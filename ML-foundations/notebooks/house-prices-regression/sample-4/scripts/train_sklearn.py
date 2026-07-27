"""Train the sklearn linear regression on the exact same features/split as
train_scratch.py, and save it in every format.

Run from the sample-4/ directory:  uv run python scripts/train_sklearn.py
"""

import sys
import time
from pathlib import Path

from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import MODELS_DIR, evaluate, load_split_and_scale  # noqa: E402
from serving_model import HousePriceModel  # noqa: E402


def main():
    X_train, X_test, y_train, y_test, scaler, feature_names = load_split_and_scale()
    print(f"Train: {X_train.shape}, Test: {X_test.shape}")

    model = LinearRegression()
    t0 = time.time()
    model.fit(X_train, y_train)
    train_seconds = time.time() - t0

    pred_log = model.predict(X_test)
    metrics = evaluate(y_test, pred_log)
    print(f"Trained in {train_seconds:.4f}s | {metrics}")

    from preprocessing import NUMERIC_FEATURE_COLS

    serving = HousePriceModel(
        coef=model.coef_,
        intercept=model.intercept_,
        feature_names=feature_names,
        scaler_mean=scaler.mean_,
        scaler_scale=scaler.scale_,
        numeric_feature_cols=NUMERIC_FEATURE_COLS,
        meta={
            "model_name": "sklearn",
            "training_method": "sklearn.linear_model.LinearRegression (closed-form OLS)",
            "target_transform": "log1p",
            "train_seconds": round(train_seconds, 4),
            "test_metrics": metrics,
        },
    )

    MODELS_DIR.mkdir(exist_ok=True)
    serving.save_pickle(MODELS_DIR / "sklearn_model.pkl")
    serving.save_joblib(MODELS_DIR / "sklearn_model.joblib")
    serving.save_raw_json(MODELS_DIR / "sklearn_model_raw.json")
    serving.save_raw_npz(MODELS_DIR / "sklearn_model_raw.npz")
    print(f"Saved sklearn model artifacts to {MODELS_DIR}")


if __name__ == "__main__":
    main()
