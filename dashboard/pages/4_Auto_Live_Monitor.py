"""Simple research-only live market dashboard with SQLite history."""
import json
import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dashboard.modern_theme import apply_modern_theme  # STAGE 19 MODERN UI THEME

from analysis.history_recorder import load_history, save_analysis
from analysis.live_engine import analyze_live_candles
from analysis.smart_market import assess_market
from dashboard.signal_readiness import assess_signal_readiness
from config.market_config import MARKETS, PLATFORMS, TIMEFRAMES, create_research_config
from market_data.authorized_live_fetch import fetch_authorized_live_candles
from market_data.provider_credit_guard import ProviderCreditStatusUnknown
from market_data.live_monitor import read_monitor_state, run_monitor_poll
from market_data.twelve_data_client import DAY_LIMIT, MarketDataError, STATE_PATH

st.set_page_config(page_title="Simple Live Market Monitor", page_icon="📈", layout="wide")
apply_modern_theme()
st.title("📈 Live Market Analysis")
st.caption("Research only • No automated trades • Broker feed not verified")

with st.sidebar:
    st.header("Market settings")
    platform = st.selectbox("Platform (research label)", list(PLATFORMS), format_func=lambda k: PLATFORMS[k]["label"])
    market = st.selectbox("Market", list(MARKETS))
    symbol = st.selectbox("Symbol", list(MARKETS[market]))
    timeframe = st.selectbox("Candle timeframe", list(TIMEFRAMES))
    refresh_minutes = st.selectbox("Fetch every", [1, 3, 5], index=0, format_func=lambda x: f"{x} minute(s)")
    st.caption("1-minute candles and 1-minute fetching are different settings.")

selection = (platform, market, symbol, timeframe, refresh_minutes)
if st.session_state.get("simple_selection") != selection:
    st.session_state["simple_selection"] = selection
    st.session_state["simple_running"] = False
    st.session_state.pop("simple_result", None)
if "simple_running" not in st.session_state:
    st.session_state["simple_running"] = False

config = create_research_config(platform=platform, market=market, symbol=symbol, timeframe=timeframe, expiry_minutes=15)
# The former Stage 7.3 polling implementation cannot perform verified credit
# renewal and has no explicit, session-bounded consent. Do not present a
# misleading READY/UNKNOWN check as the authorization for auto-monitoring.
# The newer Stage 10 page is the single supported auto-monitor entry point.
st.session_state["simple_running"] = False
st.info(
    "Automatic monitoring has moved to EUR/USD — Verified-candle Research "
    "Monitor. This older page still supports explicitly approved one-shot "
    "research fetching below; a stale credit snapshot can be renewed there "
    "when the authoritative provider guard permits it."
)
if st.button("Open verified bounded automatic monitor", key="open_bounded_monitor"):
    st.switch_page("pages/10_Real_Data_Mode.py")
st.caption("Legacy automatic polling disabled; no unattended API requests from this page.")

# Credit renewal is an independently authorized *one-shot* action, not part of
# background auto-monitor polling. This control remains available even when
# the provider snapshot expires and the auto-monitor Start button is disabled.
st.divider()
st.subheader("Verified EUR/USD real-data research · one-shot")
st.caption(
    "Explicitly approved one-time fetch; 1-minute completed candles, "
    "15-minute research expiry. This is separate from automatic monitoring."
)
st.warning(
    "This operation may use up to TWO Twelve Data API credits: "
    "one fresh credit-snapshot renewal if needed, plus one normal data fetch. "
    "No retries; if blocked or timed out, preserve the audit state."
)
from dashboard.verified_live_control import approved_live_snapshot
from dashboard.credit_renewal_diagnostics import credit_renewal_readiness
# Read-only status does not attempt HTTP and never authorizes a request.
renewal_readiness = credit_renewal_readiness()
if renewal_readiness["status"] in ("BLOCKED", "UNKNOWN"):
    st.warning("Credit renewal preflight: " + renewal_readiness["reason"])
elif renewal_readiness["status"] == "FRESH":
    st.info("Credit renewal preflight: " + renewal_readiness["reason"])

consent = st.checkbox(
    "I approve up to two accounted API requests for this one-time EUR/USD research fetch",
    key="real_one_shot_consent",
)
if st.button(
    "Fetch & analyze real EUR/USD once",
    disabled=not consent,
    key="real_one_shot_button",
    type="primary",
):
    # Streamlit buttons are event-scoped; this handler runs once per click.
    try:
        with st.spinner("Requesting verified Twelve Data candles..."):
            verified = approved_live_snapshot(approved=True)
    except Exception as exc:
        # No exception text: third-party HTTP clients can embed an API key in
        # a failed request URL or error. No automatic retry is scheduled.
        st.session_state.pop("real_one_shot_result", None)
        st.error(
            "One-shot fetch blocked or failed (" + type(exc).__name__ + "). "
            "Do not retry automatically. Inspect local accounting journals."
        )
    else:
        st.session_state["real_one_shot_result"] = verified
        st.success("Verified real-data fetch and analysis completed.")

verified_display = st.session_state.get("real_one_shot_result")
if verified_display is not None:
    snapshot = verified_display["analysis"]
    if snapshot.get("stale") or snapshot.get("gaps"):
        st.warning("This saved research snapshot is stale or contains gaps. Do not interpret it as a current signal.")
    a, b, c = st.columns(3)
    a.metric("Real candles", verified_display["candles"])
    b.metric("Observed market", snapshot.get("market_condition", "N/A"))
    c.metric("Research signal", "NO TRADE")
    st.caption("Last completed candle: " + str(snapshot.get("latest_utc", "unknown")))
    st.caption("Renewal used for this request: " + str(verified_display["credits_renewed"]))
    st.write("Indicator snapshot (same fetch; no extra HTTP requests)")
    st.json(snapshot.get("indicators", {}))
    st.info(snapshot.get("market_explanation", "Research only"))
    with st.expander("Why NO TRADE?", expanded=True):
        for reason in snapshot.get("reasons", []):
            st.write("• " + str(reason))
    st.caption("Analysis only · Quotex feed parity unverified · No broker orders")



# Legacy unbounded fragment retired; use the bounded, consent-driven Stage 10 page.
