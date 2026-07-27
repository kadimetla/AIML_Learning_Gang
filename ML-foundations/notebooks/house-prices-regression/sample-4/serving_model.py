"""The one artifact both training paths produce: a linear model over the
175-feature encoding in preprocessing.py, ready to serve.

Whether the coefficients came from gradient descent (scripts/train_scratch.py)
or sklearn's closed-form solver (scripts/train_sklearn.py) is irrelevant here
— by the time a model is *served*, it's just a weight vector, an intercept,
and the scaler stats needed to standardize incoming features the same way
they were standardized at training time. That's the point of this module:
inference is identical regardless of how the model was trained.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from preprocessing import NUMERIC_FEATURE_COLS, encode_raw_frame


class HousePriceModel:
    """A fitted linear model (coef + intercept) plus everything needed to
    turn a raw house record into a scaled feature vector: the ordered
    feature list and the StandardScaler's mean_/scale_ for the numeric
    columns. Predicts log1p(SalePrice); predict_price() back-transforms.
    """

    def __init__(
        self,
        coef: np.ndarray,
        intercept: float,
        feature_names: list[str],
        scaler_mean: np.ndarray,
        scaler_scale: np.ndarray,
        numeric_feature_cols: list[str] = NUMERIC_FEATURE_COLS,
        meta: dict[str, Any] | None = None,
    ):
        self.coef = np.asarray(coef, dtype=np.float64)
        self.intercept = float(intercept)
        self.feature_names = list(feature_names)
        self.numeric_feature_cols = list(numeric_feature_cols)
        self.scaler_mean = np.asarray(scaler_mean, dtype=np.float64)
        self.scaler_scale = np.asarray(scaler_scale, dtype=np.float64)
        self.meta = meta or {}

        if len(self.coef) != len(self.feature_names):
            raise ValueError("coef and feature_names must be the same length")
        if len(self.scaler_mean) != len(self.numeric_feature_cols):
            raise ValueError("scaler_mean must match numeric_feature_cols length")

    def _to_scaled_matrix(self, encoded: pd.DataFrame) -> np.ndarray:
        aligned = encoded.reindex(columns=self.feature_names, fill_value=0.0)
        X = aligned.to_numpy(dtype=np.float64)
        numeric_idx = [self.feature_names.index(c) for c in self.numeric_feature_cols]
        X[:, numeric_idx] = (X[:, numeric_idx] - self.scaler_mean) / self.scaler_scale
        return X

    def predict_log(self, raw_df: pd.DataFrame) -> np.ndarray:
        encoded = encode_raw_frame(raw_df)
        X_scaled = self._to_scaled_matrix(encoded)
        return X_scaled @ self.coef + self.intercept

    def predict_price(self, raw_df: pd.DataFrame) -> np.ndarray:
        return np.expm1(self.predict_log(raw_df))

    # ---- pickle / joblib -------------------------------------------------
    # Both formats pickle this exact Python object. Loading either one later
    # requires this HousePriceModel class to be importable at that path —
    # that's the trade-off versus the raw format below.

    def save_pickle(self, path: str | Path) -> None:
        import pickle

        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load_pickle(cls, path: str | Path) -> "HousePriceModel":
        import pickle

        with open(path, "rb") as f:
            return pickle.load(f)

    def save_joblib(self, path: str | Path) -> None:
        joblib.dump(self, path)

    @classmethod
    def load_joblib(cls, path: str | Path) -> "HousePriceModel":
        return joblib.load(path)

    # ---- raw JSON / npz ----------------------------------------------------
    # No pickle, no joblib, no HousePriceModel class needed to load these —
    # just numpy (and pandas, for the encoding step). Trades convenience for
    # long-term portability: this file will still load in ten years, on any
    # Python version, without caring whether this class still exists.

    def to_raw_dict(self) -> dict[str, Any]:
        return {
            "feature_names": self.feature_names,
            "numeric_feature_cols": self.numeric_feature_cols,
            "coef": self.coef.tolist(),
            "intercept": self.intercept,
            "scaler_mean": self.scaler_mean.tolist(),
            "scaler_scale": self.scaler_scale.tolist(),
            "meta": self.meta,
        }

    def save_raw_json(self, path: str | Path) -> None:
        with open(path, "w") as f:
            json.dump(self.to_raw_dict(), f, indent=2)

    def save_raw_npz(self, path: str | Path) -> None:
        # npz only stores arrays, so feature_names/numeric_feature_cols go in
        # as string arrays and meta gets flattened to a JSON string array —
        # keeps this file independently loadable, same as the JSON version.
        np.savez_compressed(
            path,
            feature_names=np.array(self.feature_names),
            numeric_feature_cols=np.array(self.numeric_feature_cols),
            coef=self.coef,
            intercept=np.array(self.intercept),
            scaler_mean=self.scaler_mean,
            scaler_scale=self.scaler_scale,
            meta_json=np.array(json.dumps(self.meta)),
        )

    @classmethod
    def from_raw_dict(cls, state: dict[str, Any]) -> "HousePriceModel":
        return cls(
            coef=state["coef"],
            intercept=state["intercept"],
            feature_names=state["feature_names"],
            scaler_mean=state["scaler_mean"],
            scaler_scale=state["scaler_scale"],
            numeric_feature_cols=state["numeric_feature_cols"],
            meta=state.get("meta", {}),
        )

    @classmethod
    def load_raw_json(cls, path: str | Path) -> "HousePriceModel":
        with open(path) as f:
            return cls.from_raw_dict(json.load(f))

    @classmethod
    def load_raw_npz(cls, path: str | Path) -> "HousePriceModel":
        with np.load(path, allow_pickle=False) as data:
            return cls(
                coef=data["coef"],
                intercept=float(data["intercept"]),
                feature_names=data["feature_names"].tolist(),
                scaler_mean=data["scaler_mean"],
                scaler_scale=data["scaler_scale"],
                numeric_feature_cols=data["numeric_feature_cols"].tolist(),
                meta=json.loads(str(data["meta_json"])),
            )
