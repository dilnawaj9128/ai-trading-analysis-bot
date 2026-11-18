"""Read-only offline market research using audited historical candles."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dashboard.modern_theme import apply_modern_theme  # STAGE 19 MODERN UI THEME

from dashboard.chart_data import (
    accepted_datasets,
    calculate_indicators,
    load_chart_candles,
    load_chart_report,
)
from dashboard.report_loader import DashboardReportError


st.set_page_config(
    page_title="Offline Market Analysis",
    page_icon="📊",
    layout="wide",
)

apply_modern_theme()
st.title("📊 Offline Market Analysis")
st.caption(
    "Historical EUR/USD research | Completed 1-minute candles | "
    "No API requests or broker execution"
)

st.warning(
    "Research only. Historical candles are not verified against "
    "Quotex execution prices. No directional trading predictions."
)

report_path = st.text_input(
    "Research report",
    value="reports/eurusd_advanced_20261112.json",
)

try:
    report = load_chart_report(Path(report_path))
    datasets = accepted_datasets(report)
except (DashboardReportError, OSError, ValueError, KeyError) as exc:
    st.error(f"Research report unavailable: {exc}")
    st.stop()

if not datasets:
    st.info("No accepted historical datasets found.")
    st.stop()

selected_dataset = st.selectbox(
    "Select audited historical dataset",
    datasets,
)

try:
    frame = load_chart_candles(selected_dataset)

    # Retains the existing data audit and indicator calculations.
    if len(frame) < 21:
        raise ValueError(
            "At least 21 candles required for EMA 21."
        )

    enriched = calculate_indicators(frame)

except (DashboardReportError, OSError, ValueError, KeyError) as exc:
    st.error(f"Dataset validation failed: {exc}")
    st.stop()

st.success("Dataset passed the existing integrity audit.")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Market", "EUR/USD")
col2.metric("Timeframe", "1 minute")
col3.metric("Historical candles", len(enriched))
col4.metric("Observation window", "15 minutes")

st.subheader("Historical Candlestick Chart")

fig = go.Figure()

fig.add_trace(
    go.Candlestick(
        x=enriched["timestamp"],
        open=enriched["Open"],
        high=enriched["High"],
        low=enriched["Low"],
        close=enriched["Close"],
        name="EUR/USD",
    )
)

for column, label in (
    ("EMA_9", "EMA 9"),
    ("EMA_21", "EMA 21"),
):
    fig.add_trace(
        go.Scatter(
            x=enriched["timestamp"],
            y=enriched[column],
            mode="lines",
            name=label,
        )
    )

fig.update_layout(
    height=520,
    xaxis_title="UTC",
    yaxis_title="Price",
    xaxis_rangeslider_visible=False,
)

st.plotly_chart(fig, width="stretch")

st.subheader("Technical Indicator Observations")

latest = enriched.iloc[-1]

a, b, c = st.columns(3)

a.metric("EMA 9", f"{latest['EMA_9']:.5f}")
b.metric("EMA 21", f"{latest['EMA_21']:.5f}")

rsi = latest["RSI_14"]
c.metric(
    "RSI 14",
    f"{rsi:.2f}" if pd.notna(rsi) else "N/A",
)

if pd.notna(latest["EMA_9"]) and pd.notna(latest["EMA_21"]):
    if latest["EMA_9"] > latest["EMA_21"]:
        st.info("Historical observation: EMA 9 is above EMA 21.")
    elif latest["EMA_9"] < latest["EMA_21"]:
        st.info("Historical observation: EMA 9 is below EMA 21.")
    else:
        st.info("Historical observation: EMAs are equal.")

st.subheader("Directional Research Safety")

st.metric("Trading action", "NO TRADE")

st.warning(
    "Directional trading action remains disabled because "
    "provider feed mode and broker execution prices have not "
    "been independently verified. This is a safety status, "
    "not a strategy-generated signal."
)

st.subheader("Recent Historical Candles")

st.dataframe(
    enriched.tail(20),
    width="stretch",
    hide_index=True,
)

st.caption(
    "Read-only local research. No Twelve Data API requests, "
    "automatic trading or forward-price predictions."
)


# STAGE 19D — OFFLINE ADVANCED RESEARCH
# Source remains the audited dataset already loaded above.
from dashboard.offline_advanced import build_advanced_research

st.divider()
st.subheader("Advanced Technical Research — Historical")
try:
    advanced = build_advanced_research(frame)
except (ValueError, TypeError, KeyError) as exc:
    st.error(f"Advanced research unavailable: {exc}")
else:
    data = advanced["enriched"]
    latest_adv = advanced["latest"]
    patterns_adv = advanced["patterns"]
    assessment = advanced["assessment"]

    def display_number(value, decimals=5):
        try:
            return f"{float(value):.{decimals}f}" if pd.notna(value) else "N/A"
        except (TypeError, ValueError):
            return "N/A"

    st.caption("Calculated from audited, completed historical candles only. No new provider requests.")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("EMA 20", display_number(latest_adv.get("EMA_20")))
    k2.metric("EMA 50", display_number(latest_adv.get("EMA_50")))
    k3.metric("ATR 14", display_number(latest_adv.get("ATR_14")))
    k4.metric("Volatility 20 (%)", display_number(latest_adv.get("Volatility_20_pct"), 3))

    m1, m2, m3 = st.columns(3)
    m1.metric("MACD", display_number(latest_adv.get("MACD"), 7))
    m2.metric("MACD Signal", display_number(latest_adv.get("MACD_signal"), 7))
    m3.metric("MACD Histogram", display_number(latest_adv.get("MACD_histogram"), 7))

    st.subheader("Historical MACD")
    macd_cols = [c for c in ("MACD", "MACD_signal", "MACD_histogram") if c in data]
    if macd_cols:
        macd_chart = go.Figure()
        for col in macd_cols:
            if col == "MACD_histogram":
                macd_chart.add_trace(go.Bar(x=data["timestamp"], y=data[col], name="Histogram"))
            else:
                macd_chart.add_trace(go.Scatter(x=data["timestamp"], y=data[col], mode="lines", name=col))
        macd_chart.update_layout(height=300, xaxis_title="UTC", yaxis_title="MACD")
        st.plotly_chart(macd_chart, width="stretch")
    else:
        st.info("MACD columns not available")

    st.subheader("Historical Support / Resistance")
    sr_columns = [c for c in ("Support", "Resistance") if c in data]
    if sr_columns:
        st.dataframe(data[["timestamp", "Close"] + sr_columns].tail(12),
                     width="stretch", hide_index=True)
    else:
        st.info("Support / resistance not available")

    st.subheader("Candlestick Patterns")
    pattern_columns = ["timestamp", "Pattern", "Pattern_Direction", "Pattern_Description"]
    if all(col in patterns_adv for col in pattern_columns):
        detected = patterns_adv.loc[patterns_adv["Pattern"] != "None", pattern_columns]
        if detected.empty:
            st.info("No recognized patterns in this dataset")
        else:
            st.dataframe(detected.tail(15), width="stretch", hide_index=True)
    else:
        st.info("Pattern labels unavailable")

    st.subheader("Indicator Alignment — Historical Research")
    st.metric("Observed condition", assessment["condition"])
    st.info(assessment["explanation"])
    for observation in advanced["observations"]:
        st.caption("• " + observation)
    st.metric("Trading action", advanced["action"])
    st.warning("NO TRADE is a safety label, not the result of an expiry prediction. "
               "Historical indicator alignment does not establish trading profitability; "
               "feed provenance and broker execution prices remain unverified.")


# STAGE 19E - HISTORICAL OBSERVATION PANEL

from analysis.historical_observation import (
    HistoricalObservationError,
    evaluate_historical_window,
)
from analysis.live_engine import analyze_live_candles

st.divider()
st.subheader("15-Minute Historical Observation")

st.caption(
    "Select a completed historical candle. Indicators use only "
    "candles available at the selected observation time. "
    "The subsequent movement is shown separately."
)

if len(frame) < 75:
    st.warning(
        "At least 75 contiguous historical candles are required "
        "for this evaluation."
    )
else:
    selected_index = st.slider(
        "Historical observation candle index",
        min_value=59,
        max_value=len(frame) - 16,
        value=len(frame) - 16,
        step=1,
    )

    try:
        observation = evaluate_historical_window(
            frame,
            selected_index=selected_index,
            expiry_minutes=15,
        )

        # Only past and selected candles enter indicator analysis.
        historical_analysis = analyze_live_candles(
            observation["indicator_input"]
        )

        st.subheader("Indicators at Observation Time")

        selected_latest = historical_analysis["latest"]

        a, b, c = st.columns(3)

        a.metric(
            "RSI 14",
            f"{selected_latest['RSI_14']:.2f}",
        )
        b.metric(
            "EMA 20",
            f"{selected_latest['EMA_20']:.5f}",
        )
        c.metric(
            "EMA 50",
            f"{selected_latest['EMA_50']:.5f}",
        )

        st.caption(
            "Observation completed: "
            + observation["observation_close_utc"]
        )

        # STAGE 19F - HISTORICAL OUTCOME CHART
        from dashboard.historical_outcome_chart import (
            build_historical_outcome_chart,
        )

        st.subheader("15-Minute Historical Outcome Chart")
        st.caption(
            "The shaded area and markers show a completed historical "
            "observation window. Future candles are shown ONLY for "
            "retrospective evaluation, never for indicator calculations."
        )
        st.plotly_chart(
            build_historical_outcome_chart(frame, observation),
            width="stretch",
        )

        st.subheader("Historical 15-Minute Outcome")

        first, second, third = st.columns(3)

        first.metric(
            "Entry reference close",
            f"{observation['entry_close']:.5f}",
        )

        second.metric(
            "Close after 15 minutes",
            f"{observation['exit_close']:.5f}",
        )

        third.metric(
            "Observed movement",
            observation["historical_direction"],
        )

        st.write(
            "Price change:",
            f"{observation['price_change']:+.5f}",
        )

        st.caption(
            "Evaluation completed: "
            + observation["evaluation_close_utc"]
        )

        st.info(
            "The observed UP/DOWN/FLAT result describes what "
            "happened historically. It is not a strategy signal "
            "or a prediction made before the outcome."
        )

        st.metric("Trading action", "NO TRADE")

    except (
        HistoricalObservationError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        st.error(f"Historical evaluation unavailable: {exc}")


# STAGE 19G - HISTORICAL BATCH REPORT

from analysis.historical_batch_report import build_historical_report

st.divider()
st.subheader("Historical 15-Minute Research Report")

st.caption(
    "Non-overlapping historical observation windows. "
    "No strategy predictions, win rates, or broker execution."
)

try:
    batch_report = build_historical_report(frame)
    summary = batch_report["summary"]
    results = batch_report["results"]

    a, b, c, d = st.columns(4)

    a.metric("Observations", summary["total_observations"])
    b.metric("Historical UP", summary["up"])
    c.metric("Historical DOWN", summary["down"])
    d.metric("Historical FLAT", summary["flat"])

    st.metric(
        "Average price movement",
        f"{summary['average_price_change']:+.5f}",
    )

    st.dataframe(
        results,
        width="stretch",
        hide_index=True,
    )

    st.download_button(
        label="Download Historical Research CSV",
        data=results.to_csv(index=False).encode("utf-8"),
        file_name="historical_15min_research.csv",
        mime="text/csv",
    )

    st.info(
        "This report describes historical market movement, "
        "not bot prediction accuracy or trading profitability."
    )

except (ValueError, TypeError, KeyError) as exc:
    st.warning(f"Historical report unavailable: {exc}")


# STAGE 19H - FILTERED HISTORICAL ANALYTICS

from analysis.historical_report_analytics import (
    filter_historical_report,
    summarize_historical_report,
)

st.divider()
st.subheader("Historical Analytics & Filters")

try:
    report_data = build_historical_report(frame)["results"]

    times = sorted(
        report_data["observation_utc"].unique().tolist()
    )

    start_time, end_time = st.select_slider(
        "Select historical observation range (UTC)",
        options=times,
        value=(times[0], times[-1]),
    )

    filtered = filter_historical_report(
        report_data, start_time, end_time
    )

    stats = summarize_historical_report(filtered)

    a, b, c, d = st.columns(4)

    a.metric("Observations", stats["total"])
    b.metric("UP", stats["up"])
    c.metric("DOWN", stats["down"])
    d.metric("FLAT", stats["flat"])

    if not filtered.empty:
        st.subheader("Historical Price Movement")

        fig_movement = go.Figure()

        fig_movement.add_trace(
            go.Bar(
                x=filtered["observation_utc"],
                y=filtered["price_change"],
                name="Historical price change",
            )
        )

        fig_movement.update_layout(
            xaxis_title="Observation time (UTC)",
            yaxis_title="EUR/USD price change",
            height=350,
        )

        st.plotly_chart(fig_movement, width="stretch")

        st.subheader("Historical Outcome Distribution")

        fig_distribution = go.Figure(
            go.Pie(
                labels=["UP", "DOWN", "FLAT"],
                values=[
                    stats["up"],
                    stats["down"],
                    stats["flat"],
                ],
                hole=0.4,
            )
        )

        st.plotly_chart(fig_distribution, width="stretch")

        st.metric(
            "Average historical price change",
            f"{stats['average_change']:+.5f}",
        )

        st.dataframe(
            filtered, width="stretch", hide_index=True
        )

        st.download_button(
            "Download Filtered Research CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="filtered_historical_research.csv",
            mime="text/csv",
        )
    else:
        st.info("No observations in selected time range.")

    st.caption(
        "Descriptive historical analytics only. "
        "Not a trading signal, win rate or profitability estimate."
    )

except (ValueError, TypeError, KeyError, IndexError) as exc:
    st.warning(f"Historical analytics unavailable: {exc}")


# STAGE 19I - SIGNAL VS HISTORICAL OUTCOME

from analysis.historical_signal_comparison import (
    evaluate_historical_signal,
)

st.divider()
st.subheader("Signal vs Historical Outcome")

st.caption(
    "Research-only comparison. Strategy calculations use only "
    "candles available at the observation time."
)

if len(frame) < 75:
    st.warning(
        "At least 75 completed candles required for comparison."
    )
else:
    signal_index = st.slider(
        "Select observation for signal comparison",
        min_value=59,
        max_value=len(frame) - 16,
        value=len(frame) - 16,
        key="stage19i_signal_index",
    )

    try:
        comparison = evaluate_historical_signal(
            frame,
            selected_index=signal_index,
        )

        a, b, c = st.columns(3)

        a.metric("Strategy signal", comparison["signal"])
        b.metric(
            "Historical outcome",
            comparison["historical_outcome"],
        )
        c.metric("Comparison", comparison["comparison"])

        st.write(
            "**Observation completed:**",
            comparison["observation_utc"],
        )
        st.write(
            "**Evaluation completed:**",
            comparison["evaluation_utc"],
        )
        st.write(
            "**Candles available to strategy:**",
            comparison["candles_used_for_signal"],
        )

        st.subheader("Strategy reasoning")

        for reason in comparison["reasons"]:
            st.write("- " + reason)

        if comparison["signal"] == "NO TRADE":
            st.info(
                "The strategy correctly remains blocked by its "
                "data provenance and quality safety gates. "
                "The historical outcome is not a prediction."
            )

        st.warning(
            "Feed verification is incomplete. "
            "Prediction accuracy and broker profitability "
            "cannot be established from this result."
        )

    except (ValueError, TypeError, KeyError) as exc:
        st.error(f"Signal comparison unavailable: {exc}")


# STAGE 19J - PROVENANCE DASHBOARD

from analysis.provenance_audit import summarize_provenance
from data.dataset_quality import audit_dataset
from simulator.session_research import CSV_NAME, RECEIPT_NAME

st.divider()
st.subheader("Dataset Provenance & Verification")

try:
    dataset_directory = Path(selected_dataset)

    audit = audit_dataset(
        dataset_directory / CSV_NAME,
        dataset_directory / RECEIPT_NAME,
    )

    provenance = summarize_provenance(audit)

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Dataset Integrity",
        provenance["dataset_integrity"],
    )

    col2.metric(
        "Provider Feed",
        provenance["provider_feed_verification"],
    )

    col3.metric(
        "Broker Prices",
        provenance["broker_price_verification"],
    )

    if provenance["directional_evaluation_allowed"]:
        st.success("Directional evaluation eligible")
    else:
        st.warning(
            "Directional evaluation is not authorized. "
            "Historical research remains available."
        )

    with st.expander("Verification details"):
        for reason in provenance["reasons"]:
            st.write("- " + reason)

        for warning in audit.get("warnings", []):
            st.caption("Audit warning: " + str(warning))

except (OSError, ValueError, TypeError, KeyError) as exc:
    st.error(f"Provenance audit unavailable: {exc}")


# STAGE 19K.2 - SIGNAL AUDIT HISTORY
# STAGE 19L - VERIFIED AUDIT EXPORT PANEL

from analysis.historical_audit_export import build_audit_exports
from data.dataset_quality import audit_dataset
from simulator.session_research import CSV_NAME, RECEIPT_NAME

st.divider()
st.subheader("Historical Signal Audit Trail")
st.caption(
    "Offline research records; downloads are generated from the currently "
    "selected, re-audited dataset. No trading or provider requests."
)

try:
    audit_directory = Path(selected_dataset)
    current_dataset_audit = audit_dataset(
        audit_directory / CSV_NAME,
        audit_directory / RECEIPT_NAME,
    )
    bundle = build_audit_exports(
        frame,
        dataset_audit=current_dataset_audit,
    )
except (ValueError, TypeError, KeyError, OSError) as exc:
    st.error(f"Audit history unavailable: {exc}")
else:
    st.metric("Audit records", bundle["record_count"])
    st.dataframe(bundle["table"], width="stretch", hide_index=True)
    st.download_button(
        "Download Audit CSV",
        data=bundle["csv_bytes"],
        file_name="historical_signal_audit.csv",
        mime="text/csv",
        key="stage19l_csv",
    )
    st.download_button(
        "Download Audit JSON",
        data=bundle["json_bytes"],
        file_name="historical_signal_audit.json",
        mime="application/json",
        key="stage19l_json",
    )
    st.info(
        "Historical observations only. Feed provenance and broker price "
        "parity remain unverified; these are not prediction accuracy results."
    )
