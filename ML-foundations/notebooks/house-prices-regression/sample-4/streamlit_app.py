"""Streamlit UI for the FastAPI house-price server (app/main.py).

Deliberately talks to the API over HTTP rather than importing HousePriceModel
directly — the point of this file is to be the *client* half of the
client/server split sample-4 already demonstrates, not another way to load
the models in-process.

Run both, in two terminals, from the sample-4/ directory:
  uv run uvicorn app.main:app --reload
  uv run streamlit run streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preprocessing import NOMINAL_COLS, NUMERIC_FEATURES, ORDINAL_MAPS  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "dataset" / "train.csv"
NONE_LABEL = "(none / doesn't apply)"

st.set_page_config(page_title="House Price Predictor", page_icon="🏠", layout="wide")


@st.cache_data
def load_dataset() -> pd.DataFrame:
    return pd.read_csv(DATASET_PATH)


@st.cache_data
def nominal_choices(_df: pd.DataFrame) -> dict[str, list[str]]:
    return {col: sorted(_df[col].dropna().unique().tolist()) for col in NOMINAL_COLS}


df = load_dataset()
choices = nominal_choices(df)

st.title("🏠 House Price Predictor")
st.caption(
    "Client for the sample-4 FastAPI server: two linear models (gradient descent "
    "'by hand' vs. sklearn), each loadable from pickle, joblib, or raw JSON/npz."
)

# --- sidebar: server connection + example loader --------------------------
st.sidebar.header("Server")
api_url = st.sidebar.text_input("FastAPI base URL", "http://127.0.0.1:8000")

try:
    health = requests.get(f"{api_url}/health", timeout=2).json()
    st.sidebar.success(f"Connected — {health['loaded_models']} model/format combos loaded")
except requests.exceptions.RequestException:
    st.sidebar.error(
        "Can't reach the API. Start it with:\n\n"
        "`uv run uvicorn app.main:app --reload`"
    )

st.sidebar.header("Prefill a house")
if st.sidebar.button("Load random example from dataset") or "row_idx" not in st.session_state:
    st.session_state.row_idx = int(np.random.randint(len(df)))
row = df.iloc[st.session_state.row_idx]
st.sidebar.caption(f"Row #{st.session_state.row_idx} — actual SalePrice: ${row['SalePrice']:,.0f}")

# --- form -------------------------------------------------------------
with st.form("house_form"):
    st.subheader("Numeric features")
    payload: dict = {}
    cols = st.columns(5)
    for i, name in enumerate(NUMERIC_FEATURES):
        default = float(row[name]) if pd.notna(row[name]) else 0.0
        payload[name] = cols[i % 5].number_input(name, value=default)

    st.subheader("Ordinal quality / condition features")
    st.caption("Ordered scales (e.g. Excellent > Good > Typical > Fair > Poor) encoded as integers.")
    cols = st.columns(5)
    for i, (name, mapping) in enumerate(ORDINAL_MAPS.items()):
        options = [NONE_LABEL] + list(mapping.keys())
        current = row.get(name)
        default_idx = options.index(current) if current in options else 0
        selection = cols[i % 5].selectbox(name, options, index=default_idx)
        payload[name] = None if selection == NONE_LABEL else selection

    st.subheader("Location / style features")
    st.caption("Nominal categories (no inherent order) — one-hot encoded behind the scenes.")
    cols = st.columns(4)
    for i, name in enumerate(NOMINAL_COLS):
        options = [NONE_LABEL] + choices[name]
        current = row.get(name)
        default_idx = options.index(current) if current in options else 0
        selection = cols[i % 4].selectbox(name, options, index=default_idx)
        payload[name] = None if selection == NONE_LABEL else selection

    st.divider()
    left, mid, right = st.columns([1, 1, 2])
    model_name = left.selectbox("Model", ["sklearn", "scratch"])
    format_name = mid.selectbox("Format", ["pickle", "joblib", "raw-json", "raw-npz"])
    compare_all = right.checkbox(
        "Compare all 8 model/format combinations instead", value=False
    )
    submitted = st.form_submit_button("Predict", use_container_width=True)

# --- results -------------------------------------------------------------
if submitted:
    try:
        if compare_all:
            resp = requests.post(f"{api_url}/predict/compare", json=payload, timeout=5)
        else:
            resp = requests.post(
                f"{api_url}/predict/{model_name}/{format_name}", json=payload, timeout=5
            )
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
        st.stop()

    if resp.status_code != 200:
        st.error(f"API returned {resp.status_code}: {resp.json().get('detail', resp.text)}")
        st.stop()

    data = resp.json()
    actual_price = float(row["SalePrice"])

    if compare_all:
        preds = data["predictions"]
        pred_df = pd.DataFrame(
            [{"combo": k, "predicted_price": v} for k, v in preds.items()]
        ).sort_values("combo")
        st.subheader("Predictions across every model/format combination")
        st.bar_chart(pred_df.set_index("combo")["predicted_price"])
        st.dataframe(pred_df, use_container_width=True, hide_index=True)
        st.caption(
            "All four formats for a given model should match exactly — that's the "
            "point (see sample-4/README.md). Small scratch vs. sklearn differences "
            "come from gradient descent only approximating the closed-form solution."
        )
        st.metric("Actual sale price (row #%d)" % st.session_state.row_idx, f"${actual_price:,.0f}")
    else:
        predicted = data["predicted_price"]
        c1, c2 = st.columns(2)
        c1.metric(
            f"Predicted price ({model_name} / {format_name})",
            f"${predicted:,.0f}",
            delta=f"{predicted - actual_price:,.0f} vs. actual",
        )
        c2.metric(f"Actual sale price (row #{st.session_state.row_idx})", f"${actual_price:,.0f}")
