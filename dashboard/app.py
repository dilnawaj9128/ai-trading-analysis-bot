
"""Local read-only historical research dashboard."""

from pathlib import Path

import pandas as pd
import streamlit as st
from dashboard.modern_theme import apply_modern_theme  # STAGE 19 MODERN UI THEME

from dashboard.report_loader import (
    DashboardReportError,
    dashboard_summary,
    hourly_chart_data,
    load_report,
    volatility_chart_data,
)


DEFAULT_REPORT = (
    "reports/eurusd_advanced_20261112.json"
)


def main():
    st.set_page_config(
        page_title="AI Trading Research Dashboard",
        page_icon="📊",
        layout="wide",
    )

    apply_modern_theme()
    st.title("AI Trading Research Dashboard")
    st.caption(
        "Historical EUR/USD research | UTC | Read-only"
    )

    st.warning(
        "ANALYSIS ONLY — No trading signals, "
        "broker execution, or directional backtesting. "
        "Feed provenance remains unverified."
    )

    with st.sidebar:
        st.header("Research report")

        report_path = st.text_input(
            "Local JSON report path",
            value=DEFAULT_REPORT,
        )

        st.info(
            "This dashboard only reads an existing "
            "schema v3 research report."
        )

    try:
        report = load_report(Path(report_path))
        summary = dashboard_summary(report)
    except DashboardReportError as exc:
        st.error(f"Report validation failed: {exc}")
        st.stop()

    st.subheader("Dataset overview")

    columns = st.columns(4)

    columns[0].metric(
        "Accepted sessions",
        summary["accepted_sessions"],
    )
    columns[1].metric(
        "Unique candles",
        summary["unique_candles"],
    )
    columns[2].metric(
        "Duplicates",
        summary["duplicates"],
    )
    columns[3].metric(
        "Overlaps",
        summary["overlaps"],
    )

    coverage = report[
        "advanced_analytics"
    ]["coverage"]

    st.subheader("Historical data coverage")

    left, right = st.columns(2)

    with left:
        percentage = summary["coverage_percent"]

        st.metric(
            "Observed-window coverage",
            (
                f"{percentage:.2f}%"
                if percentage is not None
                else "N/A"
            ),
        )

        st.metric(
            "Missing minutes",
            summary["missing_minutes"],
        )

    with right:
        st.write(
            "First candle:",
            coverage["first_timestamp"],
        )
        st.write(
            "Last candle:",
            coverage["last_timestamp"],
        )

        st.caption(
            "Missing minutes are calculated between "
            "the first and last accepted timestamps. "
            "Market closures are not excluded."
        )

    st.subheader("Hourly candle behavior")

    hourly = pd.DataFrame(
        hourly_chart_data(report)
    )

    if hourly.empty:
        st.info("No accepted hourly data.")
    else:
        st.bar_chart(
            hourly.set_index("hour")[
                ["average_range"]
            ]
        )

        st.dataframe(
            hourly,
            width="stretch",
            hide_index=True,
        )

    st.subheader("Historical volatility ranking")

    ranking = pd.DataFrame(
        volatility_chart_data(report)
    )

    if ranking.empty:
        st.info("No accepted sessions to rank.")
    else:
        st.bar_chart(
            ranking.set_index("session")[
                ["average_range"]
            ]
        )

        st.dataframe(
            ranking,
            width="stretch",
            hide_index=True,
        )

    st.subheader("Session quality and selection")

    sessions = report.get("sessions", [])

    if sessions:
        session_rows = []

        for item in sessions:
            session_rows.append({
                "Dataset": item.get("dataset"),
                "Quality": item.get("quality", {}).get(
                    "status", "UNKNOWN"
                ) if isinstance(
                    item.get("quality"), dict
                ) else "See report",
                "Selection": item.get(
                    "selection_status"
                ),
                "Reason": item.get(
                    "selection_reason"
                ),
            })

        st.dataframe(
            pd.DataFrame(session_rows),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No session records.")

    with st.expander("Research limitations"):
        for limitation in report.get(
            "limitations", []
        ):
            st.write("-", limitation)

    st.divider()

    st.caption(
        "Research-only visualization. "
        "Historical volatility does not predict "
        "future price direction."
    )


if __name__ == "__main__":
    main()

