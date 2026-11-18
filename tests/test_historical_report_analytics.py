import pandas as pd
import pytest

from analysis.historical_report_analytics import (
    filter_historical_report,
    summarize_historical_report,
)


@pytest.fixture
def sample_report():
    return pd.DataFrame({
        "observation_utc": [
            "2026-11-12T10:00:00+00:00",
            "2026-11-12T10:15:00+00:00",
            "2026-11-12T10:30:00+00:00",
        ],
        "price_change": [0.0002, -0.0001, 0.0],
        "historical_direction": ["UP", "DOWN", "FLAT"],
    })


def test_filter_utc_range(sample_report):
    result = filter_historical_report(
        sample_report,
        "2026-11-12T10:00:00+00:00",
        "2026-11-12T10:15:00+00:00",
    )
    assert len(result) == 2


def test_timezone_conversion(sample_report):
    result = filter_historical_report(
        sample_report,
        "2026-11-12T15:30:00+05:30",
        "2026-11-12T15:30:00+05:30",
    )
    assert len(result) == 1
    assert result.iloc[0]["historical_direction"] == "UP"


def test_invalid_date_range(sample_report):
    with pytest.raises(ValueError):
        filter_historical_report(
            sample_report,
            "2026-11-12T11:00:00+00:00",
            "2026-11-12T10:00:00+00:00",
        )


def test_summary_counts(sample_report):
    stats = summarize_historical_report(sample_report)

    assert stats["total"] == 3
    assert stats["up"] == 1
    assert stats["down"] == 1
    assert stats["flat"] == 1
    assert stats["average_change"] == pytest.approx(
        0.0001 / 3
    )


def test_invalid_direction_rejected(sample_report):
    sample_report.loc[0, "historical_direction"] = "INVALID"

    with pytest.raises(ValueError):
        summarize_historical_report(sample_report)


def test_empty_summary(sample_report):
    stats = summarize_historical_report(
        sample_report.iloc[:0]
    )

    assert stats["total"] == 0
    assert stats["average_change"] is None
