
import json

import pandas as pd
import pytest

from simulator.advanced_research import (
    build_advanced_research,
    export_advanced_research,
)
from tests.test_dataset_quality import (
    make_dataset,
    update_hash,
)
from tests.test_session_research_overlap import (
    shifted_dataset,
)


def test_single_session_analytics(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    report = build_advanced_research([
        csv_path.parent
    ])

    analytics = report["advanced_analytics"]

    assert report["schema_version"] == 3
    assert report["datasets_accepted"] == 1
    assert analytics["coverage"]["observed_minutes"] == 120
    assert analytics["coverage"]["missing_minutes"] == 0
    assert len(analytics["hourly_utc"]) == 2
    assert report["directional_backtesting_allowed"] is False


def test_hourly_candle_counts(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    report = build_advanced_research([
        csv_path.parent
    ])

    hourly = report["advanced_analytics"]["hourly_utc"]

    assert [item["candle_count"] for item in hourly] == [
        60, 60
    ]
    assert hourly[0]["bullish"] == 60
    assert hourly[1]["bullish"] == 60


def test_duplicate_not_double_counted(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    report = build_advanced_research([
        csv_path.parent,
        csv_path.parent,
    ])

    assert report["datasets_duplicate"] == 1
    assert report["total_valid_candles"] == 120

    analytics = report["advanced_analytics"]

    assert (
        analytics["combined_candle_statistics"]["candle_count"]
        == 120
    )


def test_non_overlapping_sessions(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=120,
    )

    report = build_advanced_research([
        first.parent,
        second,
    ])

    analytics = report["advanced_analytics"]

    assert report["datasets_accepted"] == 2
    assert report["total_valid_candles"] == 240
    assert analytics["coverage"]["missing_minutes"] == 0
    assert len(analytics["hourly_utc"]) == 4


def test_coverage_gap_between_sessions(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=180,
    )

    report = build_advanced_research([
        first.parent,
        second,
    ])

    coverage = report["advanced_analytics"]["coverage"]

    assert coverage["observed_minutes"] == 240
    assert coverage["expected_minutes"] == 300
    assert coverage["missing_minutes"] == 60
    assert len(coverage["missing_intervals"]) == 1


def test_volatility_ranking(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=120,
    )

    csv_path = second / "eurusd_1min_utc.csv"
    receipt_path = second / "acquisition.json"

    frame = pd.read_csv(csv_path)

    # Increase the range while keeping valid OHLC values.
    frame["High"] = 1.1020
    frame["Low"] = 1.0980

    frame.to_csv(csv_path, index=False)
    update_hash(csv_path, receipt_path)

    report = build_advanced_research([
        first.parent,
        second,
    ])

    ranking = report[
        "advanced_analytics"
    ]["volatility_ranking"]

    assert report["datasets_accepted"] == 2
    assert ranking[0]["dataset"] == str(second)
    assert ranking[0]["volatility_rank"] == 1
    assert (
        ranking[0]["average_range"]
        > ranking[1]["average_range"]
    )


def test_invalid_dataset_excluded(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    frame = pd.read_csv(csv_path)
    frame.loc[0, "High"] = 0.5
    frame.to_csv(csv_path, index=False)

    update_hash(csv_path, receipt_path)

    report = build_advanced_research([
        csv_path.parent
    ])

    assert report["datasets_failed"] == 1
    assert report["datasets_accepted"] == 0
    assert report["total_valid_candles"] == 0

    analytics = report["advanced_analytics"]

    assert analytics["coverage"]["observed_minutes"] == 0
    assert analytics["hourly_utc"] == []
    assert analytics["volatility_ranking"] == []


def test_export_research_only(tmp_path):
    csv_path, _ = make_dataset(
        tmp_path / "dataset"
    )

    report = build_advanced_research([
        csv_path.parent
    ])

    output = tmp_path / "advanced_report.json"

    export_advanced_research(report, output)

    payload = json.loads(output.read_text())

    assert payload["schema_version"] == 3
    assert payload["analysis_only"] is True
    assert (
        payload["directional_backtesting_allowed"]
        is False
    )
    assert "advanced_analytics" in payload

    report["directional_backtesting_allowed"] = True

    with pytest.raises(ValueError, match="safety"):
        export_advanced_research(
            report,
            tmp_path / "unsafe.json",
        )

