"""FastAPI server for the house-price linear models.

Demonstrates that inference is identical regardless of:
  - how the model was trained (gradient descent "by hand" vs sklearn), and
  - which format it was loaded from (pickle, joblib, or raw JSON/npz).

Run from the sample-4/ directory:
  uv run uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, create_model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from preprocessing import NOMINAL_COLS, NUMERIC_FEATURES, ORDINAL_MAPS  # noqa: E402
from serving_model import HousePriceModel  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DATASET_PATH = Path(__file__).resolve().parent.parent / "dataset" / "train.csv"


class ModelName(str, Enum):
    scratch = "scratch"
    sklearn = "sklearn"


class ModelFormat(str, Enum):
    pickle = "pickle"
    joblib = "joblib"
    raw_json = "raw-json"
    raw_npz = "raw-npz"


_LOADERS = {
    ModelFormat.pickle: HousePriceModel.load_pickle,
    ModelFormat.joblib: HousePriceModel.load_joblib,
    ModelFormat.raw_json: HousePriceModel.load_raw_json,
    ModelFormat.raw_npz: HousePriceModel.load_raw_npz,
}
_FILENAMES = {
    ModelFormat.pickle: "{name}_model.pkl",
    ModelFormat.joblib: "{name}_model.joblib",
    ModelFormat.raw_json: "{name}_model_raw.json",
    ModelFormat.raw_npz: "{name}_model_raw.npz",
}

# ---------------------------------------------------------------------------
# Request schema, built from the same column lists preprocessing.py uses to
# encode features — one source of truth for "what a raw house record looks
# like", instead of a hand-typed schema that could silently drift out of
# sync with the encoder.
# ---------------------------------------------------------------------------
_numeric_fields = {name: (float, Field(...)) for name in NUMERIC_FEATURES}
_ordinal_fields = {
    name: (Optional[str], Field(default=None, description=f"one of {list(mapping)} or null"))
    for name, mapping in ORDINAL_MAPS.items()
}
_nominal_fields = {name: (Optional[str], Field(default=None)) for name in NOMINAL_COLS}

HouseFeatures = create_model(
    "HouseFeatures",
    __config__=ConfigDict(extra="ignore"),
    **_numeric_fields,
    **_ordinal_fields,
    **_nominal_fields,
)


class PredictionResponse(BaseModel):
    model: ModelName
    format: ModelFormat
    log_prediction: float
    predicted_price: float


class CompareResponse(BaseModel):
    predictions: dict[str, float]


# ---------------------------------------------------------------------------
# Load every (model, format) combination once at startup rather than per
# request — the realistic pattern for serving a model that doesn't change
# between requests. MODELS stays a plain dict; FastAPI's lifespan just
# controls when it gets populated/cleared.
# ---------------------------------------------------------------------------
MODELS: dict[tuple[ModelName, ModelFormat], HousePriceModel] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = []
    for model_name in ModelName:
        for fmt in ModelFormat:
            path = MODELS_DIR / _FILENAMES[fmt].format(name=model_name.value)
            if not path.exists():
                missing.append(str(path))
                continue
            MODELS[(model_name, fmt)] = _LOADERS[fmt](path)
    if missing:
        print(f"Warning: missing model artifacts (run scripts/train_*.py first): {missing}")
    print(f"Loaded {len(MODELS)} model/format combinations")
    yield
    MODELS.clear()


app = FastAPI(
    title="House Prices — Linear Model Serving Demo",
    description=(
        "Two linear models (gradient descent 'by hand' vs. sklearn's closed-form OLS), "
        "each saved as pickle, joblib, and a dependency-light raw JSON/npz format."
    ),
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok", "loaded_models": len(MODELS)}


@app.get("/models")
def list_models():
    return {
        f"{name.value}/{fmt.value}": MODELS[(name, fmt)].meta
        for (name, fmt) in MODELS
    }


@app.get("/example")
def example_payload():
    """A real, valid house record from the training set, for trying POST /predict/*."""
    df = pd.read_csv(DATASET_PATH)
    row = df.iloc[0].drop(labels=["SalePrice", "Id"])
    return {
        "raw_house": row.where(row.notna(), None).to_dict(),
        "actual_sale_price": float(df.iloc[0]["SalePrice"]),
    }


def _predict_one(model: HousePriceModel, house: BaseModel) -> tuple[float, float]:
    raw_df = pd.DataFrame([house.model_dump()])
    log_pred = float(model.predict_log(raw_df)[0])
    return log_pred, float(np.expm1(log_pred))


@app.post("/predict/{model_name}/{format}", response_model=PredictionResponse)
def predict(model_name: ModelName, format: ModelFormat, house: HouseFeatures):  # type: ignore[valid-type]
    model = MODELS.get((model_name, format))
    if model is None:
        raise HTTPException(
            status_code=404,
            detail=f"No loaded model for {model_name.value}/{format.value}. "
            "Run scripts/train_scratch.py and scripts/train_sklearn.py first.",
        )
    log_pred, price_pred = _predict_one(model, house)
    return PredictionResponse(
        model=model_name, format=format, log_prediction=log_pred, predicted_price=price_pred
    )


@app.post("/predict/compare", response_model=CompareResponse)
def predict_compare(house: HouseFeatures):  # type: ignore[valid-type]
    """Run the same house through every loaded (model, format) combination.

    All four formats for a given model should return the same number —
    that's the point. scratch vs. sklearn may differ slightly since gradient
    descent only approximates the closed-form OLS solution.
    """
    predictions = {}
    for (model_name, fmt), model in MODELS.items():
        _, price_pred = _predict_one(model, house)
        predictions[f"{model_name.value}/{fmt.value}"] = round(price_pred, 2)
    return CompareResponse(predictions=predictions)
