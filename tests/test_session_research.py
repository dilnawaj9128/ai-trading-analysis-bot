
import json

import pandas as pd
import pytest

from simulator.session_research import (
    analyze_session,
    analyze_multiple_sessions,
    export_research_report,
)

from tests.test_dataset_quality import (
    make_dataset,
    update_hash,
)


def test_valid_session_statistics(tmp_path):
    csv_path, receipt_path = make_dataset(
        tmp_path / "dataset"
    )

    result = analyze_session(csv_path.parent)

    assert result["status"] == "PASS"
    assert result["statistics"]["candle_count"] == 120
    assert result["statistics"]["bullish_candles"] == 120
    assert result["statistics"]["bearish_candles"] == 0
    assert (
        result["directional_backtesting_allowed"]
        is False
    )


def test_invalid_session_is_not_analyzed(tmp_path):
    csv_path, receipt_path = make_dataset(
        tmp_path / "dataset"
    )

    frame = pd.read_csv(csv_path)
    frame.loc[0, "High"] = 0.5
    frame.to_csv(csv_path, index=False)

    update_hash(csv_path, receipt_path)

    result = analyze_session(csv_path.parent)

    assert result["status"] == "FAIL"
    assert result["statistics"] is None


def test_multiple_sessions_aggregate(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    from tests.test_session_research_overlap import (
        shifted_dataset,
    )

    second_dir = shifted_dataset(
        tmp_path / "second",
        minutes=120,
    )

    report = analyze_multiple_sessions([
        first.parent,
        second_dir,
    ])

    assert report["datasets_requested"] == 2
    assert report["datasets_passed"] == 2
    assert report["total_valid_candles"] == 240
    assert report["analysis_only"] is True


def test_empty_dataset_list_rejected():
    with pytest.raises(ValueError):
        analyze_multiple_sessions([])


def test_json_export(tmp_path):
    csv_path, _ = make_dataset(
        tmp_path / "dataset"
    )

    report = analyze_multiple_sessions([
        csv_path.parent
    ])

    output = tmp_path / "research_report.json"

    export_research_report(report, output)

    payload = json.loads(output.read_text())

    assert payload["datasets_passed"] == 1
    assert payload["analysis_only"] is True
    assert (
        payload["directional_backtesting_allowed"]
        is False
    )


def test_export_cannot_overwrite_source(tmp_path):
    csv_path, _ = make_dataset(
        tmp_path / "dataset"
    )

    report = analyze_multiple_sessions([
        csv_path.parent
    ])

    with pytest.raises(ValueError, match="overwrite"):
        export_research_report(
            report,
            csv_path,
        )


def test_export_rejects_trading_permission(tmp_path):
    csv_path, _ = make_dataset(
        tmp_path / "dataset"
    )

    report = analyze_multiple_sessions([
        csv_path.parent
    ])

    report["directional_backtesting_allowed"] = True

    with pytest.raises(ValueError, match="safety"):
        export_research_report(
            report,
            tmp_path / "report.json",
        )

