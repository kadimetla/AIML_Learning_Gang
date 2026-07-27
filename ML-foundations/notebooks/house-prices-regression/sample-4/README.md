# House Prices — By Hand vs. scikit-learn, Served by FastAPI

Two linear regression models trained on the same 175-feature encoding (numeric
+ ordinal quality scales + one-hot categoricals — the scheme validated in
`../sample-3`), saved in three serialization formats each, and served by a
single FastAPI app so you can compare both models and all formats side by
side.

- **`scratch_model.py`** — linear regression fit "by hand": the Adam
  optimizer implemented from scratch on top of numpy, no sklearn estimator.
- **`sklearn`** *(via `sklearn.linear_model.LinearRegression`)* — the
  closed-form OLS solution.

Both converge to essentially the same fit (test R² ≈ 0.89–0.90) — the point
isn't which one wins, it's that **inference doesn't care how a linear model
was trained**. Once you have a coefficient vector and an intercept, serving
it is identical either way.

## How to run

All commands below are run from this directory (`sample-4/`). Requires
Python 3.13 and [`uv`](https://docs.astral.sh/uv/).

### 1. Install dependencies

```bash
uv sync
```

Installs everything in `pyproject.toml` (FastAPI, scikit-learn, Streamlit,
etc.) into a local `.venv`, resolved from `uv.lock`.

### 2. Train both models

```bash
uv run python scripts/train_scratch.py    # gradient descent, by hand
uv run python scripts/train_sklearn.py    # sklearn's closed-form OLS
```

Each prints its test-set R²/RMSE and writes 4 files to `models/`
(`{name}_model.pkl`, `.joblib`, `_raw.json`, `_raw.npz`) — 8 files total.
Re-run either script any time (e.g. after editing `scratch_model.py`) to
regenerate its 4 artifacts; the API only picks up new files on its next
startup.

### 3. Start the API server

```bash
uv run uvicorn app.main:app --reload
```

Loads all 8 model/format combinations at startup and serves them at
`http://127.0.0.1:8000`. Open `http://127.0.0.1:8000/docs` for interactive
Swagger docs, or confirm it's up from another terminal:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","loaded_models":8}
```

Leave this terminal running — steps 4 and 5 both talk to it.

### 4. Call it directly with curl (optional)

```bash
curl http://127.0.0.1:8000/example > house.json         # save a real house payload
python3 -c "import json; d=json.load(open('house.json')); json.dump(d['raw_house'], open('house.json','w'))"

curl -X POST http://127.0.0.1:8000/predict/sklearn/raw-json \
  -H "Content-Type: application/json" -d @house.json

curl -X POST http://127.0.0.1:8000/predict/compare \
  -H "Content-Type: application/json" -d @house.json      # all 8 model/format combos at once
```

### 5. Or use the Streamlit UI (optional)

In a **second terminal** (keep the API running in the first):

```bash
uv run streamlit run streamlit_app.py
```

Opens `http://127.0.0.1:8501` — a form prefilled from a random real house
(sidebar button to load a different one) that POSTs to the FastAPI server
from step 3. Pick a single model/format to see one prediction, or check
"Compare all 8 model/format combinations" to bar-chart every combo against
the house's actual sale price. It talks to the API over HTTP — it's the
client half of the client/server split, not another way to load the models
in-process.

### 6. Stop everything

`Ctrl+C` in each terminal. If either was started in the background:

```bash
pkill -f "uvicorn app.main:app"
pkill -f "streamlit run streamlit_app.py"
```

## Layout

```
preprocessing.py     Raw Kaggle columns -> 175-feature encoding. Imported by
                      both training scripts and the API, so encoding logic
                      never has two implementations to drift apart.
scratch_model.py      LinearRegressionScratch — gradient descent (Adam) in
                      plain numpy, sklearn-shaped .fit()/.predict()/.coef_ API.
serving_model.py      HousePriceModel — the servable artifact: coef + intercept
                      + scaler stats + feature order. Both training scripts
                      produce one of these; it's what actually gets saved.
scripts/
  common.py            Shared train-time data loading/split/scaling.
  train_scratch.py      Trains LinearRegressionScratch, saves 4 formats.
  train_sklearn.py       Trains sklearn's LinearRegression, saves 4 formats.
models/                8 files: {scratch,sklearn}_model.{pkl,joblib} and
                      {scratch,sklearn}_model_raw.{json,npz}.
app/main.py            FastAPI server: loads all 8 at startup, one
                      /predict/{model}/{format} endpoint for all of them.
streamlit_app.py        UI client: a form that POSTs to the FastAPI server
                      above and charts the results. Not a second way to load
                      models — it never imports HousePriceModel directly.
```

## The three formats, and what "inference" actually does with each

All three store the exact same information — a coefficient vector, an
intercept, and the scaler's mean/scale per feature — but differ in *how*
that gets reconstructed into something you can call `.predict()` on.

| | **pickle** | **joblib** | **raw JSON / npz** |
|---|---|---|---|
| What's stored | A byte-serialized `HousePriceModel` Python object (via `pickle.dump`) | Same object, via `joblib.dump` (splits large numpy arrays out for more efficient storage — negligible difference at this model's size, but matters for e.g. a 500MB scikit-learn forest) | Plain data: `feature_names`, `coef`, `intercept`, `scaler_mean`, `scaler_scale`, `meta` — no Python object at all |
| To load | `pickle.load()` **re-executes** enough to reconstruct the object graph — the `HousePriceModel` class must be importable at the exact same qualified path (`serving_model.HousePriceModel`) it was pickled from | Same requirement as pickle — `joblib` is pickle underneath, with a different array codec | `json.load()` / `np.load()` — plain data, no class import needed |
| Version coupling | Fragile: a numpy/sklearn/Python version mismatch between save and load can silently break or refuse to unpickle | Same fragility as pickle | None — a JSON float is a JSON float in any language, forever |
| Security | **Never unpickle a file from an untrusted source** — unpickling can execute arbitrary code by design | Same risk (joblib delegates to pickle) | Safe to load from anywhere — it's inert data, not executable |
| Where it shines | Quick local iteration when save/load always happens in the same environment | Production sklearn pipelines with large numpy-array-heavy models | Cross-language serving, long-term archival, or handing a model to a service that shouldn't need your Python model class at all |

`app/main.py`'s `/predict/{model}/{format}` endpoint loads all four at
startup via `HousePriceModel.load_pickle` / `.load_joblib` / `.load_raw_json`
/ `.load_raw_npz`, and calls the exact same `.predict_price()` method
regardless of which one it got — see `serving_model.py` for how each load
path reconstructs an identical object.

## How a request becomes a prediction

1. **`app/main.py`** validates the POST body against `HouseFeatures` — a
   Pydantic model generated from `preprocessing.py`'s column lists, so the
   API schema can't drift from what the encoder actually expects.
2. **`preprocessing.encode_raw_frame()`** turns the raw house (numeric
   values, `"Gd"`/`"TA"`/... quality strings, `"CollgCr"`-style category
   strings) into the 175-column encoded representation: ordinal columns
   become integers, nominal columns become one-hot indicator columns.
3. **`HousePriceModel._to_scaled_matrix()`** reindexes those columns to the
   frozen training-time `feature_names` order (any category not seen in this
   one request — most neighborhoods, for a single house — becomes 0), then
   standardizes the numeric columns using the *training* scaler's saved
   mean/scale (never refit on the request).
4. `X_scaled @ coef + intercept` gives `log1p(SalePrice)`; `expm1()` back-transforms
   to a dollar prediction.

Step 3 is the one real gotcha this project hit: `pd.get_dummies(...,
drop_first=True)` decides which category to drop from *whatever's in the
current call* — fine on 1,400 training rows, silently wrong on a single
inference row (drops the request's only category, zeroing out real signal).
`preprocessing.py` one-hot-encodes every category unconditionally now;
`scripts/common.py` drops the reference column exactly once, at training
time, so `feature_names` is what encodes "drop_first" from then on —
independent of how many rows a given call happens to see.
