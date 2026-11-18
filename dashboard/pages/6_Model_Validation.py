"""Offline-only model validation readiness dashboard."""

from pathlib import Path

import streamlit as st

from analysis.training_dataset import build_training_dataset
from analysis.validation_readiness import check_validation_readiness
from dashboard.chart_data import (
    accepted_datasets,
    load_chart_candles,
    load_chart_report,
)
from dashboard.report_loader import DashboardReportError
from data.dataset_quality import audit_dataset
from simulator.session_research import CSV_NAME, RECEIPT_NAME


st.set_page_config(
    page_title="Model Validation",
    page_icon="🧪",
    layout="wide",
)

st.title("Model Validation")
st.caption(
    "15-minute research | Out-of-sample readiness | Offline only"
)

st.warning(
    "Real-market prediction accuracy is not established. "
    "This page checks data sufficiency and provenance; "
    "it does not make trading predictions."
)

report_path = st.text_input(
    "Historical research report",
    value="reports/eurusd_advanced_20261112.json",
)

try:
    report = load_chart_report(Path(report_path))
    datasets = accepted_datasets(report)
except (DashboardReportError, OSError, ValueError, KeyError) as exc:
    st.error(f"Report unavailable: {exc}")
    st.stop()

if not datasets:
    st.info("No accepted historical datasets.")
    st.stop()

selected_dataset = st.selectbox(
    "Audited dataset",
    datasets,
)

try:
    directory = Path(selected_dataset)

    audit = audit_dataset(
        directory / CSV_NAME,
        directory / RECEIPT_NAME,
    )

    if audit["status"] != "PASS":
        st.error("Dataset integrity verification failed.")
        st.stop()

    frame = load_chart_candles(selected_dataset)
    training_data = build_training_dataset(frame)

    readiness = check_validation_readiness(
        audit,
        training_rows=len(training_data),
    )

except (DashboardReportError, OSError, ValueError, KeyError) as exc:
    st.error(f"Validation unavailable: {exc}")
    st.stop()

a, b, c = st.columns(3)

a.metric("Historical candles", len(frame))
b.metric("Eligible feature rows", len(training_data))
c.metric("Minimum feature rows", readiness["minimum_rows"])

st.subheader("Out-of-Sample Validation Status")
st.metric("Readiness", readiness["status"])

if readiness["blockers"]:
    st.warning("Validation is not yet eligible.")

    for reason in readiness["blockers"]:
        st.write("- " + reason)

st.subheader("What will be evaluated?")

st.write(
    "When sufficiently large and independently verified "
    "data is available, the existing walk-forward engine "
    "can evaluate chronological training and test windows."
)

st.info(
    "Planned metrics: accuracy, balanced accuracy, "
    "Brier score, fold comparison and majority baseline."
)

st.metric("Verified live-market accuracy", "Not available")

st.caption(
    "No Twelve Data requests, no automatic trades, "
    "and no unverified performance claims."
)
