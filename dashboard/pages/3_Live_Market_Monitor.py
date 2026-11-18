
"""Manual-refresh Twelve Data market monitor."""

import os

import plotly.graph_objects as go
import streamlit as st
from dashboard.modern_theme import apply_modern_theme  # STAGE 19 MODERN UI THEME

from config.market_config import (
    MARKETS,
    PLATFORMS,
    TIMEFRAMES,
    create_research_config,
)
from market_data.authorized_live_fetch import fetch_authorized_live_candles
from market_data.twelve_data_client import (
    BudgetExceeded,
    MarketDataError,
)

st.set_page_config(
    page_title="Live Market Monitor",
    page_icon="📡",
    layout="wide",
)

apply_modern_theme()
st.title("Live Market Monitor")
st.warning(
    "RESEARCH ONLY. External Twelve Data quotes are not "
    "verified against Quotex or Olymp Trade. "
    "No signals, orders or directional backtesting."
)

platform = st.selectbox(
    "Research platform",
    list(PLATFORMS),
    format_func=lambda p: PLATFORMS[p]["label"],
)

market = st.selectbox(
    "Market",
    list(MARKETS),
)

symbol = st.selectbox(
    "Symbol",
    list(MARKETS[market]),
)

timeframe = st.selectbox(
    "Candle timeframe",
    list(TIMEFRAMES),
)

polling = st.selectbox(
    "Preferred refresh interval (manual in Stage 7.2)",
    [1, 3, 5],
    index=1,
    format_func=lambda x: f"{x} minutes",
)

config = create_research_config(
    platform=platform,
    market=market,
    symbol=symbol,
    timeframe=timeframe,
    expiry_minutes=15,
)

st.caption(
    f"Selected refresh preference: {polling} minute(s). "
    "Automatic refresh is NOT enabled."
)

if not os.environ.get("TWELVE_DATA_API_KEY"):
    st.error(
        "TWELVE_DATA_API_KEY is missing. "
        "Load the .env variables before launching Streamlit."
    )
    st.stop()

if st.button("Fetch recent market candles", type="primary"):
    with st.spinner("Fetching Twelve Data candles..."):
        try:
            result = fetch_authorized_live_candles(config)
        except BudgetExceeded as exc:
            st.error(f"API budget guard: {exc}")
        except MarketDataError as exc:
            st.error(f"Market data unavailable: {exc}")
        else:
            st.session_state["live_monitor_result"] = result
            st.session_state["live_monitor_selection"] = (
                platform, market, symbol, timeframe
            )

selection = (platform, market, symbol, timeframe)

if (
    st.session_state.get("live_monitor_selection")
    == selection
):
    result = st.session_state.get("live_monitor_result")

    if result is not None:
        a, b, c, d = st.columns(4)
        a.metric("Candles", result["candles"])
        b.metric("Timestamp gaps", result["gaps"])
        c.metric(
            "Latest candle age",
            f"{result['age_seconds'] / 60:.1f} min",
        )
        d.metric(
            "Freshness",
            "STALE" if result["stale"] else "Recent",
        )

        if result["stale"]:
            st.error(
                "Market data is stale under the local "
                "freshness rule. Do not treat it as current."
            )

        if result["gaps"]:
            st.warning(
                "Timestamp gaps detected. These may reflect "
                "market closure, missing data or feed issues."
            )

        frame = result["frame"]

        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=frame["timestamp"],
                    open=frame["Open"],
                    high=frame["High"],
                    low=frame["Low"],
                    close=frame["Close"],
                    name=symbol,
                )
            ]
        )

        fig.update_layout(
            title=f"{symbol} — {timeframe} research candles",
            xaxis_title="UTC",
            yaxis_title="Price",
            height=550,
            xaxis_rangeslider_visible=False,
        )

        st.plotly_chart(fig, width="stretch")
        st.dataframe(frame.tail(20), width="stretch")

        st.caption(
            "Completed candles only. Feed is unverified "
            "against the selected trading platform. "
            "No trade recommendations."
        )


# STAGE 18.2H - PROVIDER CREDIT STATUS
from market_data.credit_dashboard_status import (
    get_credit_dashboard_status,
)

st.divider()
st.subheader("Twelve Data API Credit Status")

try:
    credit_status = get_credit_dashboard_status()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Credits Remaining",
            credit_status["credits_left"]
            if credit_status["credits_left"] is not None
            else "Unknown",
        )

    with col2:
        st.metric(
            "Credits Used",
            credit_status["credits_used"]
            if credit_status["credits_used"] is not None
            else "Unknown",
        )

    with col3:
        st.metric("Credit Status", credit_status["status"])

    if credit_status["status"] == "READY":
        st.success("Provider credit threshold satisfied")
    elif credit_status["status"] == "LOW_CREDITS":
        st.warning(credit_status["message"])
    else:
        st.info(credit_status["message"])

    st.caption(
        "Read-only provider snapshot. Actual request authorization "
        "is enforced separately by the authorization guard."
    )

except (OSError, ValueError, TypeError) as exc:
    st.error(f"Provider credit status unavailable: {exc}")
