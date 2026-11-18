"""Simple research-only live market dashboard with SQLite history."""
import json
import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.history_recorder import load_history, save_analysis
from analysis.live_engine import analyze_live_candles
from analysis.smart_market import assess_market
from config.market_config import MARKETS, PLATFORMS, TIMEFRAMES, create_research_config
from market_data.live_monitor import read_monitor_state, run_monitor_poll
from market_data.twelve_data_client import DAY_LIMIT, MarketDataError, STATE_PATH

st.set_page_config(page_title="Simple Live Market Monitor", page_icon="📈", layout="wide")
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
start_col, stop_col = st.columns(2)
with start_col:
    if st.button("▶ Start live monitoring", use_container_width=True, disabled=st.session_state["simple_running"]):
        if not os.environ.get("TWELVE_DATA_API_KEY"):
            st.error("API key missing. Load TWELVE_DATA_API_KEY before starting Streamlit.")
        else:
            st.session_state["simple_running"] = True
            st.rerun()
with stop_col:
    if st.button("■ Stop", use_container_width=True, disabled=not st.session_state["simple_running"]):
        st.session_state["simple_running"] = False
        st.rerun()

st.info("Monitoring ON" if st.session_state["simple_running"] else "Monitoring OFF — press Start to fetch candles")


def fmt(value, digits=5):
    try:
        return "N/A" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"
    except (ValueError, TypeError):
        return "N/A"


@st.fragment(run_every="10s")
def live_panel():
    if not st.session_state.get("simple_running"):
        return
    try:
        outcome = run_monitor_poll(config, interval_minutes=refresh_minutes)
    except (MarketDataError, ValueError, OSError) as exc:
        st.error(f"Monitoring unavailable: {exc}")
        return

    status = outcome["status"]
    if status == "SUCCESS":
        st.session_state["simple_result"] = outcome["result"]
        st.session_state["simple_last_fetch"] = datetime.now(timezone.utc).isoformat()
    elif status == "WAITING":
        st.caption("Next permitted fetch: " + outcome["next_allowed_utc"])
    elif status == "BUDGET_BLOCKED":
        st.error("Local API request budget reached. Fetching paused.")
    else:
        st.error("Fetch failed: " + outcome.get("reason", "Unknown error"))

    result = st.session_state.get("simple_result")
    if result is None:
        st.info("Waiting for the first successful API fetch.")
        return
    try:
        analysis = analyze_live_candles(result["frame"])
        enriched = analysis["frame"]
        latest = analysis["latest"]
        timestamp = pd.Timestamp(result["latest_utc"])
        if timestamp.tzinfo is None:
            raise ValueError("Latest candle has no timezone")
        age = max(0, (datetime.now(timezone.utc) - timestamp.to_pydatetime()).total_seconds())
        stale = age > {"1min": 60, "5min": 300, "15min": 900}[timeframe] * 3
        gaps = result["gaps"]
    except (ValueError, TypeError, KeyError) as exc:
        st.error(f"Analysis unavailable: {exc}")
        return

    if stale or gaps or status != "SUCCESS":
        st.warning("Caution: " + "; ".join([
            *(["latest candle is stale"] if stale else []),
            *([f"{gaps} missing candle interval(s)"] if gaps else []),
            *(["showing last successful fetch"] if status != "SUCCESS" else []),
        ]))

    smart = assess_market(analysis, stale=stale, gaps=gaps)

    # Save history only for a newly successful fetch, never on WAITING
    # fragment reruns. The database operation makes no API requests.
    if status == "SUCCESS":
        try:
            record_id = save_analysis(
                symbol=config.symbol,
                timeframe=config.timeframe,
                analysis=analysis,
                assessment=smart,
            )
            st.caption(f"Analysis history saved (record #{record_id}).")
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            st.warning(f"Could not save analysis history: {exc}")
    st.subheader("Smart Market Assessment")
    st.metric("Market condition", smart["condition"])
    st.info(smart["explanation"])
    st.caption("Research-only indicator alignment, not an expiry or directional prediction.")

    trend = "Mixed / neutral"
    e9, e21 = latest.get("EMA_9"), latest.get("EMA_21")
    if pd.notna(e9) and pd.notna(e21):
        trend = "EMA 9 above EMA 21" if e9 > e21 else ("EMA 9 below EMA 21" if e9 < e21 else "EMAs equal")
    a, b, c = st.columns(3)
    a.metric("Latest close", fmt(latest.get("Close")))
    b.metric("EMA observation", trend)
    c.metric("Data age", f"{age / 60:.1f} min")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=enriched["timestamp"], open=enriched["Open"], high=enriched["High"], low=enriched["Low"], close=enriched["Close"], name="Price"))
    for key, name in (("EMA_9", "EMA 9"), ("EMA_21", "EMA 21")):
        fig.add_trace(go.Scatter(x=enriched["timestamp"], y=enriched[key], mode="lines", name=name))
    fig.update_layout(title=f"{symbol} • {timeframe} completed candles", height=470, xaxis_rangeslider_visible=False, margin=dict(l=15, r=15, t=45, b=20))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("What the indicators say")
    rsi = latest.get("RSI_14")
    rsi_text = "Not enough data" if pd.isna(rsi) else ("Above 70: high RSI reading" if rsi > 70 else ("Below 30: low RSI reading" if rsi < 30 else "Between 30–70: middle range"))
    st.write(f"**RSI 14:** {fmt(rsi, 1)} — {rsi_text}")
    st.write(f"**EMA 9 / 21:** {trend}. This describes the recent price trend, not the next candle.")
    for observation in analysis["observations"]:
        st.caption("• " + observation)
    st.caption("These observations are not UP/DOWN predictions or trading recommendations.")

    with st.expander("Advanced details (MACD, ATR, patterns, raw candles, credits)"):
        st.write("**ATR 14:**", fmt(latest.get("ATR_14")))
        macd_cols = [col for col in enriched.columns if "MACD" in col.upper()]
        if macd_cols:
            st.write("**MACD — latest candles**")
            st.dataframe(enriched[["timestamp"] + macd_cols].tail(5), use_container_width=True)
        levels = [col for col in enriched.columns if "support" in col.lower() or "resistance" in col.lower()]
        if levels:
            st.write("**Support / resistance**")
            st.dataframe(enriched[["timestamp"] + levels].tail(3), use_container_width=True)
        patterns = analysis["patterns"]
        cols = ["Pattern", "Pattern_Direction", "Pattern_Description"]
        if all(col in patterns.columns for col in cols):
            st.write("**Recent candlestick patterns**")
            st.dataframe(patterns[["timestamp"] + cols].tail(5), use_container_width=True)
        st.write("**Recent completed candles**")
        st.dataframe(result["frame"].tail(5), use_container_width=True)
        try:
            st.write("**Scheduler:**", read_monitor_state().get("last_status", "Unknown"))
        except (OSError, ValueError, MarketDataError):
            st.write("Scheduler state unavailable")
        try:
            if STATE_PATH.exists():
                usage = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                used = usage.get("day_used", 0) if usage.get("day") == today else 0
                st.write(f"**Estimated local daily credits:** {used} / {DAY_LIMIT}")
        except (OSError, ValueError, TypeError):
            st.write("Credit estimate unavailable")

        st.write("**Recent saved analyses**")
        try:
            history = load_history(limit=10)
            if history:
                st.dataframe(
                    pd.DataFrame(history)[
                        ["recorded_at", "symbol", "timeframe", "market_condition"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No saved analysis records yet.")
        except (OSError, ValueError, sqlite3.Error) as exc:
            st.caption(f"History unavailable: {exc}")


live_panel()
