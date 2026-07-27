"""Shared feature engineering for the house-prices models.

Used by both training scripts (scripts/train_*.py) and the FastAPI app, so the
exact same encoding logic runs at train time and at inference time. This is
the same 175-feature scheme validated in sample-3's neural-network notebook:
10 numeric predictors, ~20 ordinal quality/condition scales, and ~22 one-hot
nominal columns. ``Utilities`` is intentionally excluded (see sample-3): it's
1457/1458 rows "AllPub", so standardizing it turns the one outlier row into
an 18-sigma spike that destabilizes training for no real predictive gain.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

NUMERIC_FEATURES = [
    "OverallQual", "GrLivArea", "GarageCars", "GarageArea", "TotalBsmtSF",
    "1stFlrSF", "FullBath", "TotRmsAbvGrd", "YearBuilt", "YearRemodAdd",
]

_QUALITY_SCALE = {"Ex": 5, "Gd": 4, "TA": 3, "Fa": 2, "Po": 1}
_QUALITY_COLS = [
    "ExterQual", "ExterCond", "BsmtQual", "BsmtCond", "HeatingQC",
    "FireplaceQu", "GarageQual", "GarageCond", "PoolQC", "KitchenQual",
]

ORDINAL_MAPS = {
    **{c: _QUALITY_SCALE for c in _QUALITY_COLS},
    "BsmtExposure": {"Gd": 4, "Av": 3, "Mn": 2, "No": 1},
    "BsmtFinType1": {"GLQ": 6, "ALQ": 5, "BLQ": 4, "Rec": 3, "LwQ": 2, "Unf": 1},
    "BsmtFinType2": {"GLQ": 6, "ALQ": 5, "BLQ": 4, "Rec": 3, "LwQ": 2, "Unf": 1},
    "GarageFinish": {"Fin": 3, "RFn": 2, "Unf": 1},
    "Functional": {"Typ": 8, "Min1": 7, "Min2": 6, "Mod": 5, "Maj1": 4, "Maj2": 3, "Sev": 2, "Sal": 1},
    "Fence": {"GdPrv": 4, "MnPrv": 3, "GdWo": 2, "MnWw": 1},
    "LandSlope": {"Gtl": 3, "Mod": 2, "Sev": 1},
    "LotShape": {"Reg": 4, "IR1": 3, "IR2": 2, "IR3": 1},
    "PavedDrive": {"Y": 3, "P": 2, "N": 1},
    "CentralAir": {"Y": 1, "N": 0},
}
ORDINAL_ENCODED_COLS = [c + "_enc" for c in ORDINAL_MAPS]

NOMINAL_COLS = [
    "Neighborhood", "MSZoning", "Street", "Alley", "LandContour", "LotConfig",
    "Condition1", "Condition2", "BldgType", "HouseStyle", "RoofStyle", "RoofMatl",
    "Exterior1st", "Exterior2nd", "MasVnrType", "Foundation", "Heating", "Electrical",
    "GarageType", "MiscFeature", "SaleType", "SaleCondition",
]

# Columns a raw house record must supply (or leave null/omit for "doesn't have it").
RAW_COLUMNS = NUMERIC_FEATURES + list(ORDINAL_MAPS) + NOMINAL_COLS

# The scaler only applies to continuous numeric + integer-ordinal columns —
# one-hot dummy columns are already 0/1 and standardizing them (see sample-3)
# blows up rare categories into extreme z-scores.
NUMERIC_FEATURE_COLS = NUMERIC_FEATURES + ORDINAL_ENCODED_COLS


def encode_raw_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Turn raw Kaggle-style columns into the numeric + ordinal + one-hot feature frame.

    NaN in an ordinal quality column means "doesn't have this feature" (no
    basement, no garage, ...) and is mapped to rank 0. NaN in a nominal column
    is mapped to the literal category "None" before one-hot encoding, matching
    how pd.get_dummies was fit at training time.
    """
    out = df.copy()

    for col, mapping in ORDINAL_MAPS.items():
        out[col + "_enc"] = out[col].map(mapping).fillna(0) if col in out else 0.0

    for col in NOMINAL_COLS:
        if col not in out:
            out[col] = "None"
    out[NOMINAL_COLS] = out[NOMINAL_COLS].fillna("None")
    # No drop_first here: pd.get_dummies(drop_first=True) decides which
    # category to drop from *whatever categories are present in this call*.
    # That's fine on a full training set but breaks at inference — a
    # single-row request only has one category per column, so drop_first
    # would silently zero out that entire column instead of encoding it.
    # Every category gets its own column here; the "reference" category is
    # dropped exactly once, downstream in scripts/common.py, by keeping only
    # the columns present in the frozen training-time feature_names list.
    nominal_dummies = pd.get_dummies(out[NOMINAL_COLS], prefix=NOMINAL_COLS)

    for col in NUMERIC_FEATURES:
        if col not in out:
            out[col] = np.nan

    return pd.concat([out[NUMERIC_FEATURES], out[ORDINAL_ENCODED_COLS], nominal_dummies], axis=1)


def align_to_feature_names(df_encoded: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Reindex an encoded frame to the exact training-time column set/order.

    Inference requests rarely contain every one-hot category seen at training
    time (e.g. a single house can't be in 25 different neighborhoods at once),
    so missing dummy columns are filled with 0 rather than treated as an error.
    """
    return df_encoded.reindex(columns=feature_names, fill_value=0.0)
