
"""Verified, read-only historical candle chart preparation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dashboard.report_loader import (
    DashboardReportError,
    load_report,
)
from data.dataset_quality import audit_dataset
from simulator.session_research import (
    CSV_NAME,
    RECEIPT_NAME,
)


COLUMNS = ("timestamp", "Open", "High", "Low", "Close")


def accepted_datasets(report):
    """Only use datasets accepted by the session selector."""

    sessions = report.get("sessions", [])

    if not isinstance(sessions, list):
        raise DashboardReportError("Invalid session records")

    selected = []

    for session in sessions:
        if not isinstance(session, dict):
            raise DashboardReportError("Invalid session entry")

        if session.get("selection_status") == "ACCEPTED":
            directory = session.get("dataset")

            if not isinstance(directory, str) or not directory:
                raise DashboardReportError(
                    "Accepted session has no dataset path"
                )

            selected.append(directory)

    if len(selected) != report["datasets_accepted"]:
        raise DashboardReportError(
            "Accepted dataset count mismatch"
        )

    return selected


def load_chart_candles(dataset_dir):
    """
    Re-audit original CSV and receipt before charting.

    No file modifications, no broker access.
    """

    directory = Path(dataset_dir)

    csv_path = directory / CSV_NAME
    receipt_path = directory / RECEIPT_NAME

    audit = audit_dataset(csv_path, receipt_path)

    if audit.get("status") != "PASS":
        raise DashboardReportError(
            "Dataset failed quality re-audit"
        )

    frame = pd.read_csv(csv_path)

    if not set(COLUMNS).issubset(frame.columns):
        raise DashboardReportError(
            "Missing OHLC or timestamp columns"
        )

    frame = frame.loc[:, COLUMNS].copy()

    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    )

    frame = frame.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    return frame


def calculate_indicators(frame):
    """
    Historical EMA 9/21 and Wilder RSI 14.

    Warmup values remain unavailable (NaN).
    No directional classification is produced.
    """

    result = frame.copy()

    closes = result["Close"].astype(float)

    result["EMA_9"] = closes.ewm(
        span=9,
        adjust=False,
        min_periods=9,
    ).mean()

    result["EMA_21"] = closes.ewm(
        span=21,
        adjust=False,
        min_periods=21,
    ).mean()

    # Wilder RSI: initial 14-period mean, then
    # recursive smoothing of gains and losses.
    period = 14
    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    rsi = pd.Series(
        float("nan"),
        index=result.index,
        dtype=float,
    )

    if len(result) > period:
        avg_gain = gains.iloc[1:period + 1].mean()
        avg_loss = losses.iloc[1:period + 1].mean()

        for index in range(period, len(result)):
            if index > period:
                avg_gain = (
                    avg_gain * (period - 1)
                    + float(gains.iloc[index])
                ) / period

                avg_loss = (
                    avg_loss * (period - 1)
                    + float(losses.iloc[index])
                ) / period

            if avg_loss == 0 and avg_gain == 0:
                value = 50.0
            elif avg_loss == 0:
                value = 100.0
            elif avg_gain == 0:
                value = 0.0
            else:
                relative_strength = avg_gain / avg_loss
                value = 100 - (
                    100 / (1 + relative_strength)
                )

            rsi.iloc[index] = value

    result["RSI_14"] = rsi

    return result


def filter_time_window(frame, start, end):
    """Inclusive UTC timestamp filter."""

    start_utc = pd.Timestamp(start)
    end_utc = pd.Timestamp(end)

    if start_utc.tzinfo is None:
        start_utc = start_utc.tz_localize("UTC")
    else:
        start_utc = start_utc.tz_convert("UTC")

    if end_utc.tzinfo is None:
        end_utc = end_utc.tz_localize("UTC")
    else:
        end_utc = end_utc.tz_convert("UTC")

    if start_utc > end_utc:
        raise ValueError("Start time must precede end time")

    return frame.loc[
        frame["timestamp"].between(
            start_utc, end_utc
        )
    ].copy()


def session_comparison(report):
    """Build descriptive comparisons from accepted sessions."""

    datasets = accepted_datasets(report)
    rows = []

    for index, directory in enumerate(
        datasets, start=1
    ):
        frame = load_chart_candles(directory)

        ranges = (
            frame["High"].astype(float)
            - frame["Low"].astype(float)
        )

        rows.append({
            "Session": index,
            "Dataset": directory,
            "Candles": len(frame),
            "Average range": float(ranges.mean()),
            "Maximum range": float(ranges.max()),
            "First UTC": frame["timestamp"].iloc[0],
            "Last UTC": frame["timestamp"].iloc[-1],
        })

    return pd.DataFrame(rows)


def load_chart_report(report_path):
    """Reuse the existing safety-validated JSON loader."""

    return load_report(report_path)

