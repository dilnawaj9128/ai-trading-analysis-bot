
"""Read-only validation and preparation of research reports."""

from __future__ import annotations

import json
import math
from pathlib import Path


class DashboardReportError(ValueError):
    pass


def _nonnegative_integer(value, name):
    if type(value) is not int or value < 0:
        raise DashboardReportError(
            f"{name} must be a non-negative integer"
        )
    return value


def _finite_nonnegative(value, name):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise DashboardReportError(
            f"{name} must be finite and non-negative"
        )
    return float(value)


def validate_report(report):
    """Reject unsupported, unsafe or inconsistent reports."""

    if not isinstance(report, dict):
        raise DashboardReportError("Report must be an object")

    if type(report.get("schema_version")) is not int:
        raise DashboardReportError("Invalid schema version")

    if report["schema_version"] != 3:
        raise DashboardReportError(
            "Only advanced research schema v3 is supported"
        )

    if report.get("analysis_only") is not True:
        raise DashboardReportError(
            "Analysis-only restriction missing"
        )

    if report.get("directional_backtesting_allowed") is not False:
        raise DashboardReportError(
            "Directional backtesting must be blocked"
        )

    counts = {}

    for key in (
        "datasets_requested",
        "datasets_passed",
        "datasets_failed",
        "datasets_accepted",
        "datasets_duplicate",
        "datasets_overlapping",
        "total_valid_candles",
    ):
        counts[key] = _nonnegative_integer(
            report.get(key), key
        )

    if (
        counts["datasets_passed"]
        + counts["datasets_failed"]
        != counts["datasets_requested"]
    ):
        raise DashboardReportError(
            "Dataset quality counts are inconsistent"
        )

    if (
        counts["datasets_accepted"]
        + counts["datasets_duplicate"]
        + counts["datasets_overlapping"]
        > counts["datasets_passed"]
    ):
        raise DashboardReportError(
            "Dataset selection counts are inconsistent"
        )

    analytics = report.get("advanced_analytics")

    if not isinstance(analytics, dict):
        raise DashboardReportError(
            "Missing advanced analytics"
        )

    coverage = analytics.get("coverage")

    if not isinstance(coverage, dict):
        raise DashboardReportError(
            "Missing coverage statistics"
        )

    observed = _nonnegative_integer(
        coverage.get("observed_minutes"),
        "observed_minutes",
    )
    expected = _nonnegative_integer(
        coverage.get("expected_minutes"),
        "expected_minutes",
    )
    missing = _nonnegative_integer(
        coverage.get("missing_minutes"),
        "missing_minutes",
    )

    if observed + missing != expected:
        raise DashboardReportError(
            "Coverage counts are inconsistent"
        )

    if observed != counts["total_valid_candles"]:
        raise DashboardReportError(
            "Observed candles do not match accepted candles"
        )

    hourly = analytics.get("hourly_utc")
    ranking = analytics.get("volatility_ranking")

    if not isinstance(hourly, list):
        raise DashboardReportError(
            "Hourly analytics must be a list"
        )

    if not isinstance(ranking, list):
        raise DashboardReportError(
            "Volatility ranking must be a list"
        )

    hourly_total = 0

    for item in hourly:
        if not isinstance(item, dict):
            raise DashboardReportError("Invalid hourly entry")

        if not isinstance(
            item.get("hour_start_utc"), str
        ):
            raise DashboardReportError(
                "Missing UTC hour label"
            )

        hourly_total += _nonnegative_integer(
            item.get("candle_count"),
            "hourly candle count",
        )

        _finite_nonnegative(
            item.get("average_range"),
            "hourly average range",
        )

    if hourly_total != observed:
        raise DashboardReportError(
            "Hourly candle totals are inconsistent"
        )

    if len(ranking) != counts["datasets_accepted"]:
        raise DashboardReportError(
            "Ranking count does not match accepted sessions"
        )

    for item in ranking:
        if not isinstance(item, dict):
            raise DashboardReportError("Invalid ranking entry")

        _nonnegative_integer(
            item.get("volatility_rank"),
            "volatility rank",
        )
        _finite_nonnegative(
            item.get("average_range"),
            "session average range",
        )

    return report


def load_report(path):
    """Read JSON without modifying the source file."""

    path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as file:
            report = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DashboardReportError(
            f"Cannot read research report: {exc}"
        ) from exc

    return validate_report(report)


def dashboard_summary(report):
    validate_report(report)

    coverage = report["advanced_analytics"]["coverage"]

    return {
        "accepted_sessions": report["datasets_accepted"],
        "unique_candles": report["total_valid_candles"],
        "duplicates": report["datasets_duplicate"],
        "overlaps": report["datasets_overlapping"],
        "coverage_percent": coverage["coverage_percent"],
        "missing_minutes": coverage["missing_minutes"],
        "analysis_only": True,
    }


def hourly_chart_data(report):
    validate_report(report)

    return [
        {
            "hour": item["hour_start_utc"],
            "average_range": item["average_range"],
            "candles": item["candle_count"],
        }
        for item in report["advanced_analytics"]["hourly_utc"]
    ]


def volatility_chart_data(report):
    validate_report(report)

    return [
        {
            "session": f"Session {item['session']}",
            "average_range": item["average_range"],
            "rank": item["volatility_rank"],
        }
        for item in report[
            "advanced_analytics"
        ]["volatility_ranking"]
    ]

