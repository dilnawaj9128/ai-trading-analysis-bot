"""Stage 27: Opt-in, bounded live research session.

Starts with one immediate approved Twelve Data fetch, then refreshes periodically.
Reuses durable probe quota/cooldown; no broker calls or automated trading.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.live_probe_readiness import inspect_probe_readiness, due_for_live_refresh
from dashboard.auto_refresh_policy import (
    MAX_CALLS, start_auto_refresh, due_for_refresh, finish_attempt,
)
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


st.divider()
st.subheader("Live Analysis Session (opt-in)")
st.caption(
    "Default OFF. Start Live Analysis fetches immediately when eligible, "
    "or waits for the remaining probe cooldown without using credits; "
    f"this browser session may make up to {MAX_CALLS} total requests. "
    "The local probe also enforces its durable budget, 3-minute cooldown and "
    "unresolved-attempt lockout. Auto mode stops after an error, 3 attempts, "
    "or 60 minutes. Each next request is at least 3 minutes after the last. "
    "No trading or broker connection."
)

session = st.session_state.get("stage26_auto")
active = isinstance(session, dict) and session.get("active") is True
if active:
    if session.get("status") == "WAITING_FOR_COOLDOWN":
        st.warning("Live session WAITING_FOR_COOLDOWN — no request has been sent during the wait.")
        st.caption("The read-only countdown updates while the browser tab stays open.")
    else:
        st.info(
            f"Live analysis RUNNING · attempts made: {session['attempts']}/{MAX_CALLS} "
            f"· next attempt no earlier than: {session['next_due_at']} UTC"
        )
    if st.button("Pause / stop live analysis"):
        st.session_state["stage26_auto"] = {
            **session, "active": False, "status": "PAUSED"
        }
        st.rerun()
else:
    interval_minutes = st.selectbox(
        "Automatic interval", [3, 5, 15], index=0,
        format_func=lambda x: f"{x} minutes", key="stage26_interval",
    )
    approval_nonce = st.session_state.get("stage26_approval_nonce", 0)
    auto_approved = st.checkbox(
        "Start now if eligible: I approve up to 3 Twelve Data requests during "
        "this browser session (maximum 60 minutes); API credits may be used.",
        value=False, key=f"stage26_auto_approval_{approval_nonce}",
    )
    if st.button(
        "Start Live Analysis — fetch now or wait for cooldown",
        type="primary", disabled=not auto_approved or not key_loaded,
    ):
        started_at = datetime.now(timezone.utc)
        readiness = inspect_probe_readiness(now=started_at)
        st.session_state["stage26_approval_nonce"] = approval_nonce + 1
        if readiness["status"] == "BLOCKED":
            st.session_state["stage26_auto_message"] = (
                "Live analysis BLOCKED: " + readiness["reason"]
            )
        else:
            initial = start_auto_refresh(
                now=started_at, minutes=interval_minutes, approved=True,
            )
            if readiness["status"] == "WAITING_FOR_COOLDOWN":
                initial["status"] = "WAITING_FOR_COOLDOWN"
                initial["next_due_at"] = (
                    started_at + timedelta(seconds=readiness["seconds_left"])
                ).isoformat()
                st.session_state["stage26_auto_message"] = (
                    "Waiting for the persistent 3-minute cooldown. "
                    "No API request attempted yet."
                )
            else:
                # Next fragment tick attempts immediately on this page rerun.
                initial["next_due_at"] = started_at.isoformat()
                st.session_state["stage26_auto_message"] = (
                    "Ready for immediate approved fetch."
                )
            st.session_state["stage26_auto"] = initial
        st.rerun()
    if session is not None:
        st.caption(f"Last auto-session state: {session.get('status', 'UNKNOWN')}")


if hasattr(st, "fragment"):
    @st.fragment(run_every="15s")
    def auto_refresh_tick():
        """Cooldown-aware, bounded session; no network until eligible."""
        current = st.session_state.get("stage26_auto")
        if not isinstance(current, dict) or not current.get("active"):
            return
        now = datetime.now(timezone.utc)
        try:
            started = datetime.fromisoformat(current["started_at"])
            if started.tzinfo is None:
                raise ValueError("Missing timezone")
            expired = now < started or now >= started + timedelta(minutes=60)
        except (ValueError, KeyError, TypeError, OverflowError):
            expired = True
        if expired:
            st.session_state["stage26_auto"] = {
                **current, "active": False, "status": "EXPIRED"
            }
            st.rerun(scope="app")
            return

        readiness = inspect_probe_readiness(now=now)
        if readiness["status"] == "BLOCKED":
            st.session_state["stage26_auto"] = {
                **current, "active": False, "status": "BLOCKED"
            }
            st.session_state["stage26_auto_message"] = (
                "Live analysis stopped: " + readiness["reason"]
            )
            st.rerun(scope="app")
            return
        if readiness["status"] == "WAITING_FOR_COOLDOWN":
            wait_until = now + timedelta(seconds=readiness["seconds_left"])
            # Preserve later user-selected polling schedule when applicable.
            try:
                configured_due = datetime.fromisoformat(current["next_due_at"])
                if configured_due.tzinfo is None:
                    raise ValueError("Naive schedule")
                wait_until = max(wait_until, configured_due)
            except (ValueError, KeyError, TypeError):
                st.session_state["stage26_auto"] = {
                    **current, "active": False, "status": "BLOCKED"
                }
                st.rerun(scope="app")
                return
            st.session_state["stage26_auto"] = {
                **current, "status": "WAITING_FOR_COOLDOWN",
                "next_due_at": wait_until.isoformat(),
            }
            st.info(f"Waiting for cooldown · about {readiness['seconds_left']} seconds remaining · 0 credits used by this check")
            return

        if current.get("status") == "WAITING_FOR_COOLDOWN":
            # Readiness is now READY, but polling interval can be later.
            current = {**current, "status": "ARMED"}
            st.session_state["stage26_auto"] = current
        if not due_for_live_refresh(current, now=now):
            return
        if not os.environ.get("TWELVE_DATA_API_KEY"):
            st.session_state["stage26_auto"] = {
                **current, "active": False, "status": "BLOCKED"
            }
            st.session_state["stage26_auto_message"] = "API key unavailable; session stopped without HTTP."
            st.rerun(scope="app")
            return

        # Reserve UI attempt slot before transport. The durable probe itself
        # rechecks cooldown under a process lock and enforces the local budget.
        staged = finish_attempt(current, now=now, successful=True)
        st.session_state["stage26_auto"] = {
            **staged, "active": False, "status": "IN_FLIGHT"
        }
        try:
            response = approved_refresh_once()
        except Exception as exc:
            st.session_state["stage26_auto"] = {
                **staged, "active": False, "status": "STOPPED_AFTER_ERROR"
            }
            st.session_state["stage26_auto_message"] = (
                "Approved request stopped (" + type(exc).__name__ + "). "
                "No retry; inspect persistent probe evidence."
            )
        else:
            st.session_state["stage26_auto"] = staged
            st.session_state["stage26_auto_message"] = (
                f"Live fetch VERIFIED: {response['candles']} completed candles, "
                f"credits at response: {response['credits_left']}."
            )
        st.rerun(scope="app")

    auto_refresh_tick()
else:
    st.warning(
        "Scheduled live research requires Streamlit st.fragment. "
        "Manual approved refresh remains available."
    )

if st.session_state.get("stage26_auto_message"):
    st.info(st.session_state["stage26_auto_message"])


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
    st.error("Saved data is stale. It needs an approved fresh fetch; refreshes may be blocked by the probe cooldown or budget.")
if hasattr(st, "fragment"):
    @st.fragment(run_every="30s")
    def live_freshness_indicator():
        age = (pd.Timestamp(datetime.now(timezone.utc)) - last_open).total_seconds()
        st.caption(f"Current saved candle age: {max(age, 0)/60:.1f} minutes "
                   f"· {'STALE' if age > STALE_LIMIT_SECONDS else 'recent'} "
                   "· read-only clock update")
    live_freshness_indicator()
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
# Distinguish technical research bias from a permitted directional signal.
if not stale and not gaps:
    condition = market.get("condition")
    if condition == "BULLISH ALIGNMENT":
        st.info("Indicator-only research bias: UP alignment (not a trade signal).")
    elif condition == "BEARISH ALIGNMENT":
        st.info("Indicator-only research bias: DOWN alignment (not a trade signal).")
    else:
        st.info("Indicator-only research bias: inconclusive.")
else:
    st.warning("Historical/stale or incomplete data: current directional assessment unavailable.")
st.caption("NO TRADE on unverified feed mode or stale data is intentional. "
           "Technical bias is not a broker-specific prediction or trade instruction.")

with st.expander("Latest 20 completed candles"):
    st.dataframe(df.tail(20), width="stretch", hide_index=True)

st.caption("Viewing stored candles uses zero API credits. Only approved manual or bounded live-session actions call Twelve Data. No orders are placed.")
