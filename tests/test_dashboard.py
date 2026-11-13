
import copy
import json

import pytest

from dashboard.report_loader import (
    DashboardReportError,
    dashboard_summary,
    hourly_chart_data,
    load_report,
    validate_report,
    volatility_chart_data,
)


@pytest.fixture
def sample_report():
    return {
        "schema_version": 3,
        "report_type": "advanced_historical_research",
        "analysis_only": True,
        "directional_backtesting_allowed": False,
        "datasets_requested": 1,
        "datasets_passed": 1,
        "datasets_failed": 0,
        "datasets_accepted": 1,
        "datasets_duplicate": 0,
        "datasets_overlapping": 0,
        "total_valid_candles": 120,
        "advanced_analytics": {
            "coverage": {
                "first_timestamp": (
                    "2026-11-12T10:00:00+00:00"
                ),
                "last_timestamp": (
                    "2026-11-12T11:59:00+00:00"
                ),
                "observed_minutes": 120,
                "expected_minutes": 120,
                "missing_minutes": 0,
                "coverage_percent": 100.0,
                "missing_intervals": [],
            },
            "hourly_utc": [
                {
                    "hour_start_utc": (
                        "2026-11-12T10:00:00+00:00"
                    ),
                    "candle_count": 60,
                    "average_range": 0.000137,
                },
                {
                    "hour_start_utc": (
                        "2026-11-12T11:00:00+00:00"
                    ),
                    "candle_count": 60,
                    "average_range": 0.000140,
                },
            ],
            "volatility_ranking": [
                {
                    "session": 1,
                    "volatility_rank": 1,
                    "average_range": 0.000139,
                }
            ],
        },
    }


def test_valid_report(sample_report):
    assert validate_report(sample_report) is sample_report


def test_summary(sample_report):
    summary = dashboard_summary(sample_report)

    assert summary["accepted_sessions"] == 1
    assert summary["unique_candles"] == 120
    assert summary["coverage_percent"] == 100.0
    assert summary["analysis_only"] is True


def test_hourly_chart(sample_report):
    data = hourly_chart_data(sample_report)

    assert len(data) == 2
    assert sum(item["candles"] for item in data) == 120


def test_volatility_chart(sample_report):
    data = volatility_chart_data(sample_report)

    assert len(data) == 1
    assert data[0]["rank"] == 1


def test_reject_trading_permission(sample_report):
    unsafe = copy.deepcopy(sample_report)
    unsafe["directional_backtesting_allowed"] = True

    with pytest.raises(DashboardReportError):
        validate_report(unsafe)


def test_reject_invalid_counts(sample_report):
    invalid = copy.deepcopy(sample_report)
    invalid["total_valid_candles"] = 240

    with pytest.raises(DashboardReportError):
        validate_report(invalid)


def test_reject_invalid_schema(sample_report):
    invalid = copy.deepcopy(sample_report)
    invalid["schema_version"] = 2

    with pytest.raises(DashboardReportError):
        validate_report(invalid)


def test_load_json_read_only(tmp_path, sample_report):
    path = tmp_path / "research.json"
    path.write_text(json.dumps(sample_report))

    before = path.read_bytes()
    loaded = load_report(path)
    after = path.read_bytes()

    assert loaded["schema_version"] == 3
    assert before == after

