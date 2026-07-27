"""Shared training-time data prep: load the Kaggle CSV, drop the well-known
GrLivArea/SalePrice outliers, encode features, split, and fit the scaler.

This is deliberately separate from preprocessing.py: encode_raw_frame() there
runs at both train time and inference time, but outlier-dropping and fitting
a StandardScaler only make sense on a full training set.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from preprocessing import NOMINAL_COLS, NUMERIC_FEATURE_COLS, encode_raw_frame  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent.parent / "dataset" / "train.csv"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def _drop_one_reference_category(encoded: pd.DataFrame) -> pd.DataFrame:
    """encode_raw_frame() one-hot encodes every category it sees (see its
    docstring for why). For a clean, non-rank-deficient OLS design matrix, a
    linear model still needs one reference category dropped per nominal
    column — done here, exactly once, on the full training set, so the
    surviving column names become the frozen `feature_names` contract that
    inference aligns to later.
    """
    drop_cols = []
    for col in NOMINAL_COLS:
        prefix = f"{col}_"
        dummy_cols = sorted(c for c in encoded.columns if c.startswith(prefix))
        if dummy_cols:
            drop_cols.append(dummy_cols[0])
    return encoded.drop(columns=drop_cols)


def load_split_and_scale(test_size: float = 0.2, random_state: int = 42):
    """Returns (X_train, X_test, y_train_log, y_test_log, scaler, feature_names)."""
    raw = pd.read_csv(DATASET_PATH)
    raw_clean = raw[~((raw["GrLivArea"] > 4000) & (raw["SalePrice"] < 300000))].copy()

    encoded = _drop_one_reference_category(encode_raw_frame(raw_clean))
    feature_names = list(encoded.columns)
    y_log = np.log1p(raw_clean["SalePrice"])

    df = pd.concat([encoded, y_log.rename("y_log")], axis=1).dropna()
    X, y = df[feature_names], df["y_log"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    scaler = StandardScaler()
    X_train_scaled = X_train.copy()
    X_test_scaled = X_test.copy()
    X_train_scaled[NUMERIC_FEATURE_COLS] = scaler.fit_transform(X_train[NUMERIC_FEATURE_COLS])
    X_test_scaled[NUMERIC_FEATURE_COLS] = scaler.transform(X_test[NUMERIC_FEATURE_COLS])

    return X_train_scaled, X_test_scaled, y_train, y_test, scaler, feature_names


def evaluate(y_test_log, pred_log) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    y_test_price = np.expm1(y_test_log)
    pred_price = np.expm1(pred_log)
    return {
        "log_r2": float(r2_score(y_test_log, pred_log)),
        "price_r2": float(r2_score(y_test_price, pred_price)),
        "price_rmse": float(np.sqrt(mean_squared_error(y_test_price, pred_price))),
        "price_mae": float(mean_absolute_error(y_test_price, pred_price)),
    }
