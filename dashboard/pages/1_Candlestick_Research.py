
"""Interactive, read-only historical chart dashboard."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dashboard.modern_theme import apply_modern_theme  # STAGE 19 MODERN UI THEME

from dashboard.chart_data import (
    accepted_datasets,
    calculate_indicators,
    filter_time_window,
    load_chart_candles,
    load_chart_report,
    session_comparison,
)
from dashboard.report_loader import DashboardReportError


DEFAULT_REPORT = "reports/eurusd_advanced_20261112.json"


def candlestick_figure(frame, show_ema9, show_ema21):
    figure = go.Figure()

    figure.add_trace(
        go.Candlestick(
            x=frame["timestamp"],
            open=frame["Open"],
            high=frame["High"],
            low=frame["Low"],
            close=frame["Close"],
            name="Historical OHLC",
        )
    )

    if show_ema9:
        figure.add_trace(
            go.Scatter(
                x=frame["timestamp"],
                y=frame["EMA_9"],
                name="EMA 9",
                mode="lines",
            )
        )

    if show_ema21:
        figure.add_trace(
            go.Scatter(
                x=frame["timestamp"],
                y=frame["EMA_21"],
                name="EMA 21",
                mode="lines",
            )
        )

    figure.update_layout(
        title="Historical 1-minute OHLC",
        xaxis_title="UTC time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=550,
        hovermode="x unified",
    )

    return figure


def rsi_figure(frame):
    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=frame["timestamp"],
            y=frame["RSI_14"],
            mode="lines",
            name="RSI 14",
        )
    )

    # Reference levels are descriptive only.
    for level in (30, 70):
        figure.add_hline(
            y=level,
            line_dash="dash",
        )

    figure.update_layout(
        title="Historical RSI 14",
        xaxis_title="UTC time",
        yaxis_title="RSI",
        yaxis=dict(range=[0, 100]),
        height=320,
    )

    return figure


def main():
    st.set_page_config(
        page_title="Candlestick Research",
        page_icon="📈",
        layout="wide",
    )

    apply_modern_theme()
    st.title("Historical Candlestick Research")

    st.warning(
        "ANALYSIS ONLY — Historical visualization. "
        "No BUY/SELL signals, broker orders, or "
        "directional backtesting. Feed provenance "
        "remains unverified."
    )

    with st.sidebar:
        st.header("Chart settings")

        report_path = st.text_input(
            "Advanced research JSON",
            value=DEFAULT_REPORT,
        )

        show_ema9 = st.checkbox(
            "Show EMA 9", value=True
        )

        show_ema21 = st.checkbox(
            "Show EMA 21", value=True
        )

        show_rsi = st.checkbox(
            "Show RSI 14", value=True
        )

    try:
        report = load_chart_report(
            Path(report_path)
        )

        datasets = accepted_datasets(report)

    except (DashboardReportError, ValueError) as exc:
        st.error(f"Report validation failed: {exc}")
        st.stop()

    if not datasets:
        st.info("No accepted historical sessions.")
        st.stop()

    selected = st.selectbox(
        "Choose an accepted historical session",
        options=datasets,
    )

    try:
        raw_frame = load_chart_candles(selected)
        frame = calculate_indicators(raw_frame)
    except (DashboardReportError, ValueError, OSError) as exc:
        st.error(f"Cannot load candles: {exc}")
        st.stop()

    first = frame["timestamp"].iloc[0]
    last = frame["timestamp"].iloc[-1]

    st.caption(
        f"Available historical window: "
        f"{first.isoformat()} to {last.isoformat()}"
    )

    start_col, end_col = st.columns(2)

    with start_col:
        start_time = st.slider(
            "Start UTC",
            min_value=first.to_pydatetime(),
            max_value=last.to_pydatetime(),
            value=first.to_pydatetime(),
            format="YYYY-MM-DD HH:mm",
        )

    with end_col:
        end_time = st.slider(
            "End UTC",
            min_value=first.to_pydatetime(),
            max_value=last.to_pydatetime(),
            value=last.to_pydatetime(),
            format="YYYY-MM-DD HH:mm",
        )

    if start_time > end_time:
        st.error("Start time must not exceed end time.")
        st.stop()

    visible = filter_time_window(
        frame, start_time, end_time
    )

    if visible.empty:
        st.info("No candles in selected time window.")
        st.stop()

    col1, col2, col3 = st.columns(3)

    col1.metric("Visible candles", len(visible))

    col2.metric(
        "Average candle range",
        f"{(visible['High'] - visible['Low']).mean():.8f}",
    )

    col3.metric(
        "Last historical close",
        f"{visible['Close'].iloc[-1]:.5f}",
    )

    st.plotly_chart(
        candlestick_figure(
            visible, show_ema9, show_ema21
        ),
        width="stretch",
    )

    if show_rsi:
        st.plotly_chart(
            rsi_figure(visible),
            width="stretch",
        )

    with st.expander("Historical OHLC and indicators"):
        st.dataframe(
            visible,
            width="stretch",
            hide_index=True,
        )

    st.subheader("Accepted session comparison")

    try:
        comparison = session_comparison(report)
    except (DashboardReportError, ValueError, OSError) as exc:
        st.error(f"Comparison unavailable: {exc}")
        st.stop()

    if not comparison.empty:
        st.dataframe(
            comparison,
            width="stretch",
            hide_index=True,
        )

        st.bar_chart(
            comparison.set_index("Session")[
                ["Average range"]
            ]
        )

    st.caption(
        "EMA and RSI are historical indicators, "
        "not predictions. RSI reference levels "
        "do not trigger trades."
    )


if __name__ == "__main__":
    main()

