"""Stage 25: Saved-candle dashboard with an explicitly approved manual refresh.

Never fetch automatically; uses existing durable, budgeted research probe.
No broker interaction or trade execution.
"""

from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.live_engine import analyze_live_candles
from analysis.smart_market import assess_market
from dashboard.modern_theme import apply_modern_theme
from strategy.signal_engine import generate_signal

CSV_PATH = Path("data/real_market/latest_eurusd_completed.csv")
INTERVAL = pd.Timedelta(minutes=1)
STALE_LIMIT_SECONDS = 180


def load_saved_candles(path: Path) -> tuple[pd.DataFrame, int]:
    """Validate UTC order, completed OHLC, duplicates and continuity."""
    if not path.is_file():
        raise ValueError(f"Saved CSV missing: {path}")
    frame = pd.read_csv(path)
    required = {"timestamp", "Open", "High", "Low", "Close"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing CSV columns: {sorted(required - set(frame.columns))}")
    if len(frame) < 60:
        raise ValueError("At least 60 completed candles are required")

    frame = frame[["timestamp", "Open", "High", "Low", "Close"]].copy()
    raw_stamps = frame["timestamp"].astype(str)
    if not raw_stamps.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise ValueError("All timestamps must contain an explicit timezone")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if frame["timestamp"].isna().any() or frame["timestamp"].duplicated().any():
        raise ValueError("Missing or duplicate candle timestamps")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("Candles must be in ascending time order")
    if (frame["timestamp"].dt.second != 0).any() or (frame["timestamp"].dt.microsecond != 0).any():
        raise ValueError("Candles must align to whole minutes")

    import numpy as np
    for field in ("Open", "High", "Low", "Close"):
        frame[field] = pd.to_numeric(frame[field], errors="raise")
    values = frame[["Open", "High", "Low", "Close"]]
    if not np.isfinite(values.to_numpy(dtype=float)).all() or (values <= 0).any().any():
        raise ValueError("Candles contain missing, nonfinite, or nonpositive prices")
    if not (frame["High"] >= frame[["Open", "Low", "Close"]].max(axis=1)).all():
        raise ValueError("Invalid High OHLC relationship")
    if not (frame["Low"] <= frame[["Open", "High", "Close"]].min(axis=1)).all():
        raise ValueError("Invalid Low OHLC relationship")
    gaps = int((frame["timestamp"].diff().iloc[1:] != INTERVAL).sum())
    return frame, gaps


def approved_refresh_once():
    """Call existing single-request probe without changing its authorization rules."""
    if not os.environ.get("TWELVE_DATA_API_KEY"):
        raise RuntimeError("API key is not loaded in the Streamlit process")
    probe_path = Path("scripts/approved_real_data_probe.py")
    if not probe_path.is_file():
        raise RuntimeError("Existing approved real-data probe script is missing")
    spec = importlib.util.spec_from_file_location("approved_real_data_probe", probe_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load approved probe script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # This operation may reserve a local API credit and perform exactly one
    # real request. The probe persists an attempt before transport and never
    # automatically retries unresolved requests.
    return module.probe_once(approved=True)


def display_value(value, digits=5):
    return f"{float(value):.{digits}f}" if pd.notna(value) else "N/A"


st.set_page_config(page_title="Real Data Research", page_icon="📈", layout="wide")
apply_modern_theme()
st.title("📈 Twelve Data — Real Market Research")
st.caption("EUR/USD · 1-minute completed candles · local CSV · 15-minute research expiry")
st.warning("Research only. The optional manual refresh performs one Twelve Data API request and may consume credits. No broker connection or trade execution. Feed mode and Quotex price parity are unverified.")

st.subheader("Manual market-data refresh")
st.caption("No background polling. Each approved click attempts at most one request. The existing probe enforces a 3-minute cooldown, persistent attempt evidence, and the local credit budget.")
preference = st.selectbox(
    "Preferred refresh interval (manual only)",
    [1, 3, 5, 15],
    index=2,
    format_func=lambda value: f"{value} minutes",
)
st.caption(f"Your preference: {preference} minutes. The probe's minimum 3-minute cooldown still applies; this choice does not schedule requests.")
key_loaded = bool(os.environ.get("TWELVE_DATA_API_KEY"))
if not key_loaded:
    st.info("For real refresh, load TWELVE_DATA_API_KEY before starting Streamlit. Saved CSV remains viewable.")

nonce = st.session_state.get("stage25_approval_nonce", 0)
approved = st.checkbox(
    "I approve ONE real Twelve Data request, which may consume API credits.",
    value=False,
    key=f"stage25_manual_approval_{nonce}",
)
left_button, right_button = st.columns(2)
with left_button:
    refresh_requested = st.button(
        "Fetch fresh EUR/USD candles (one request)",
        type="primary",
        disabled=not approved or not key_loaded,
    )
with right_button:
    reload_requested = st.button("Reload saved CSV")

if refresh_requested:
    # Clear approval before initiating transport: a Streamlit rerun cannot
    # silently authorize an additional request.
    st.session_state["stage25_approval_nonce"] = nonce + 1
    with st.spinner("Running one approved Twelve Data request..."):
        try:
            result = approved_refresh_once()
        except Exception as exc:
            # requests exceptions may embed the URL and API key. Never show
            # exception messages or remote response content in browser.
            st.session_state["stage25_fetch_message"] = (
                "Attempt BLOCKED / FAILED (" + type(exc).__name__ + "). "
                "If unresolved, do not retry or delete state files."
            )
        else:
            st.session_state["stage25_fetch_message"] = (
                f"Validated {result['candles']} completed candles; "
                f"provider credits at response: {result['credits_left']}. "
                "Existing authorization- and feed-mode caveats still apply."
            )
    st.rerun()

if reload_requested:
    st.rerun()

if st.session_state.get("stage25_fetch_message"):
    st.info(st.session_state["stage25_fetch_message"])


try:
    df, gaps = load_saved_candles(CSV_PATH)
    analyzed = analyze_live_candles(df)
except (OSError, ValueError, TypeError, KeyError, pd.errors.ParserError) as exc:
    st.error(f"Dataset or indicator validation failed: {exc}")
    st.stop()

now = pd.Timestamp(datetime.now(timezone.utc))
last_open = df["timestamp"].iloc[-1]
last_close = last_open + INTERVAL
age_seconds = (now - last_open).total_seconds()
stale = age_seconds > STALE_LIMIT_SECONDS or now < last_close
# The imported saved CSV is not independently verified to be a live/delayed feed.
# Never override the signal engine's data-mode and stale-data guards.
quality = "VALID" if gaps == 0 and not stale else "INVALID"
signal = generate_signal(
    analyzed["frame"], expiry_minutes=15,
    data_mode="unknown", data_quality_status=quality,
)
market = assess_market(analyzed, stale=stale, gaps=gaps)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Completed candles", len(df))
c2.metric("Last close", display_value(df["Close"].iloc[-1], 5))
c3.metric("Timestamp gaps", gaps)
c4.metric("Freshness", "STALE" if stale else "Recent")
st.caption(f"Last candle opened (UTC): {last_open.isoformat()} · age: {age_seconds / 60:.1f} min · expiry: 15 min")
if stale:
    st.error("Stored data is stale for current-market analysis. Reloading the page does not fetch new candles; only a separately approved manual request can.")
if gaps:
    st.warning("Dataset has one or more missing 1-minute candle slots.")

st.subheader("Completed-candle price chart")
enriched = analyzed["frame"]
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=df["timestamp"], open=df["Open"], high=df["High"],
    low=df["Low"], close=df["Close"], name="EUR/USD",
))
for col, name in (("EMA_20", "EMA 20"), ("EMA_50", "EMA 50")):
    fig.add_trace(go.Scatter(x=df["timestamp"], y=enriched[col], mode="lines", name=name))
fig.update_layout(height=510, xaxis_rangeslider_visible=False, xaxis_title="UTC", yaxis_title="EUR/USD")
st.plotly_chart(fig, width="stretch")

st.subheader("Indicators calculated by your existing engine")
latest = analyzed["latest"]
m1, m2, m3, m4 = st.columns(4)
m1.metric("RSI 14", display_value(latest.get("RSI_14"), 2))
m2.metric("EMA 20", display_value(latest.get("EMA_20"), 6))
m3.metric("EMA 50", display_value(latest.get("EMA_50"), 6))
m4.metric("ATR 14", display_value(latest.get("ATR_14"), 7))
n1, n2 = st.columns(2)
n1.metric("MACD", display_value(latest.get("MACD"), 7))
n2.metric("MACD signal", display_value(latest.get("MACD_signal"), 7))

st.subheader("Market condition and research signal")
st.info(f"Market condition: **{market['condition']}** — {market['explanation']}")
st.metric("Signal engine output (15-minute expiry)", signal["signal"])
for reason in signal.get("reasons", []):
    st.write("•", reason)
st.caption("NO TRADE on unknown feed mode or stale data is intentional. An analysis result is not a prediction guarantee.")

with st.expander("Latest 20 completed candles"):
    st.dataframe(df.tail(20), width="stretch", hide_index=True)

st.caption("Viewing and reloading saved data use zero API credits. Only the explicit manual fetch button can call the provider; no orders are ever placed.")
