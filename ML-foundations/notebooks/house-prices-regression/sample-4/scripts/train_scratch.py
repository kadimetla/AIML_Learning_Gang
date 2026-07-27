"""Train the "by hand" linear regression (scratch_model.LinearRegressionScratch,
gradient descent implemented with plain numpy) and save it in every format.

Run from the sample-4/ directory:  uv run python scripts/train_scratch.py
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import MODELS_DIR, evaluate, load_split_and_scale  # noqa: E402
from scratch_model import LinearRegressionScratch  # noqa: E402
from serving_model import HousePriceModel  # noqa: E402


def main():
    X_train, X_test, y_train, y_test, scaler, feature_names = load_split_and_scale()
    print(f"Train: {X_train.shape}, Test: {X_test.shape}")

    X_train_np = X_train.to_numpy(dtype=np.float64)
    X_test_np = X_test.to_numpy(dtype=np.float64)

    model = LinearRegressionScratch(learning_rate=0.03, n_iters=20_000, verbose_every=4000)
    t0 = time.time()
    model.fit(X_train_np, y_train.to_numpy(dtype=np.float64))
    train_seconds = time.time() - t0

    pred_log = model.predict(X_test_np)
    metrics = evaluate(y_test, pred_log)
    print(f"Trained in {train_seconds:.2f}s | {metrics}")

    from preprocessing import NUMERIC_FEATURE_COLS

    # scaler was fit on X_train[NUMERIC_FEATURE_COLS], so mean_/scale_ are
    # already ordered to match that column list exactly.
    serving = HousePriceModel(
        coef=model.coef_,
        intercept=model.intercept_,
        feature_names=feature_names,
        scaler_mean=scaler.mean_,
        scaler_scale=scaler.scale_,
        numeric_feature_cols=NUMERIC_FEATURE_COLS,
        meta={
            "model_name": "scratch",
            "training_method": "gradient descent (Adam, numpy, no sklearn estimator)",
            "target_transform": "log1p",
            "train_seconds": round(train_seconds, 2),
            "n_iters": model.n_iters,
            "final_train_loss": model.loss_history_[-1],
            "test_metrics": metrics,
        },
    )

    MODELS_DIR.mkdir(exist_ok=True)
    serving.save_pickle(MODELS_DIR / "scratch_model.pkl")
    serving.save_joblib(MODELS_DIR / "scratch_model.joblib")
    serving.save_raw_json(MODELS_DIR / "scratch_model_raw.json")
    serving.save_raw_npz(MODELS_DIR / "scratch_model_raw.npz")
    print(f"Saved scratch model artifacts to {MODELS_DIR}")


if __name__ == "__main__":
    main()
