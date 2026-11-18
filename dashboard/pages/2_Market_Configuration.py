
"""Stage 7.1 Streamlit multi-platform research selector."""

import json

import streamlit as st

from config.market_config import (
    MARKETS,
    PLATFORMS,
    TIMEFRAMES,
    ResearchConfigError,
    create_research_config,
    research_disclaimer,
)


def main():
    st.set_page_config(
        page_title="Market Configuration",
        page_icon="🌍",
        layout="wide",
    )

    st.title("Multi-Market Research Configuration")

    st.warning(
        "ANALYSIS ONLY. No live API requests, "
        "broker connection, trading signals or "
        "automatic orders are enabled."
    )

    st.subheader("Select your research profile")

    platform = st.selectbox(
        "Trading platform research profile",
        options=list(PLATFORMS),
        format_func=lambda key: PLATFORMS[key]["label"],
    )

    market = st.selectbox(
        "Market category",
        options=list(MARKETS),
        format_func=lambda key: key.upper(),
    )

    symbol = st.selectbox(
        "Market symbol",
        options=list(MARKETS[market]),
    )

    timeframe = st.selectbox(
        "Historical candle timeframe",
        options=list(TIMEFRAMES),
        format_func=lambda key: {
            "1min": "1 minute",
            "5min": "5 minutes",
            "15min": "15 minutes",
        }[key],
    )

    expiry = st.selectbox(
        "Research observation / expiry window",
        options=[15],
        format_func=lambda value: f"{value} minutes",
    )

    try:
        config = create_research_config(
            platform=platform,
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            expiry_minutes=expiry,
        )
    except ResearchConfigError as exc:
        st.error(str(exc))
        st.stop()

    st.divider()

    st.subheader("Selected configuration")

    left, middle, right = st.columns(3)

    left.metric(
        "Platform",
        PLATFORMS[config.platform]["label"],
    )
    middle.metric("Symbol", config.symbol)
    right.metric("Timeframe", config.timeframe)

    st.info(research_disclaimer(config))

    st.subheader("Research safety status")

    st.write("Analysis only:", config.analysis_only)
    st.write("Execution enabled:", config.execution_enabled)
    st.write(
        "Broker feed verified:",
        config.broker_feed_verified,
    )
    st.write(
        "Provider feed verified:",
        config.provider_feed_verified,
    )
    st.write(
        "Directional backtesting allowed:",
        config.directional_backtesting_allowed,
    )

    st.subheader("Configuration JSON")

    st.json(config.to_dict())

    st.caption(
        "This selection does not change the existing "
        "EUR/USD historical reports or charts. "
        "Stage 7.2 will introduce separately validated "
        "market-data ingestion."
    )


if __name__ == "__main__":
    main()

