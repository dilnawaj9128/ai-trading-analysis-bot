import json
import shutil

import pandas as pd

from simulator.session_research import (
    analyze_multiple_sessions,
    export_research_report,
)
from tests.test_dataset_quality import (
    make_dataset,
    update_hash,
)


def shifted_dataset(tmp_path, minutes, conflict=False):
    """Create a structurally valid shifted test dataset."""

    csv_path, receipt_path = make_dataset(tmp_path)

    frame = pd.read_csv(csv_path)

    timestamps = pd.to_datetime(
        frame["timestamp"], utc=True
    ) + pd.Timedelta(minutes=minutes)

    frame["timestamp"] = [
        timestamp.isoformat()
        for timestamp in timestamps
    ]

    if conflict:
        # Still valid OHLC, but different from first dataset.
        frame["Close"] = 1.1003

    frame.to_csv(csv_path, index=False)

    receipt = json.loads(receipt_path.read_text())

    for key in (
        "requested_start",
        "requested_end",
        "retrieved_at",
    ):
        receipt[key] = (
            pd.Timestamp(receipt[key])
            + pd.Timedelta(minutes=minutes)
        ).isoformat()

    receipt_path.write_text(json.dumps(receipt))
    update_hash(csv_path, receipt_path)

    return csv_path.parent


def test_single_session_accepted(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    report = analyze_multiple_sessions([
        csv_path.parent
    ])

    assert report["datasets_accepted"] == 1
    assert report["total_valid_candles"] == 120
    assert report["sessions"][0]["selection_status"] == "ACCEPTED"


def test_same_directory_duplicate(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    report = analyze_multiple_sessions([
        csv_path.parent,
        csv_path.parent,
    ])

    assert report["datasets_accepted"] == 1
    assert report["datasets_duplicate"] == 1
    assert report["total_valid_candles"] == 120
    assert report["sessions"][1]["selection_reason"] == "SAME_DIRECTORY"


def test_identical_csv_in_different_directory(tmp_path):
    first, first_receipt = make_dataset(
        tmp_path / "first"
    )

    second_dir = tmp_path / "second"
    second_dir.mkdir()

    shutil.copy2(
        first,
        second_dir / first.name,
    )
    shutil.copy2(
        first_receipt,
        second_dir / first_receipt.name,
    )

    report = analyze_multiple_sessions([
        first.parent,
        second_dir,
    ])

    assert report["datasets_duplicate"] == 1
    assert report["datasets_accepted"] == 1
    assert report["total_valid_candles"] == 120
    assert report["sessions"][1]["selection_reason"] == "IDENTICAL_CSV"


def test_non_overlapping_sessions(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=120,
    )

    report = analyze_multiple_sessions([
        first.parent,
        second,
    ])

    assert report["datasets_accepted"] == 2
    assert report["datasets_duplicate"] == 0
    assert report["datasets_overlapping"] == 0
    assert report["total_valid_candles"] == 240


def test_overlapping_sessions_excluded(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=60,
    )

    report = analyze_multiple_sessions([
        first.parent,
        second,
    ])

    assert report["datasets_accepted"] == 1
    assert report["datasets_overlapping"] == 1
    assert report["total_valid_candles"] == 120
    assert report["overlaps"][0]["overlap_count"] == 60
    assert (
        report["sessions"][1]["selection_reason"]
        == "REPEATED_TIMESTAMPS"
    )


def test_conflicting_prices_detected(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=60,
        conflict=True,
    )

    report = analyze_multiple_sessions([
        first.parent,
        second,
    ])

    assert report["datasets_overlapping"] == 1
    assert (
        report["overlaps"][0]["conflicting_candle_count"]
        == 60
    )
    assert (
        report["sessions"][1]["selection_reason"]
        == "CONFLICTING_PRICES"
    )


def test_combined_statistics_do_not_double_count(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=120,
    )

    report = analyze_multiple_sessions([
        first.parent,
        first.parent,
        second,
    ])

    stats = report["combined_statistics"]

    assert stats["candle_count"] == 240
    assert stats["bullish_candles"] == 240
    assert stats["bearish_candles"] == 0
    assert stats["doji_candles"] == 0
    assert report["datasets_duplicate"] == 1


def test_report_export_preserves_selection(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    report = analyze_multiple_sessions([
        first.parent,
        first.parent,
    ])

    output = tmp_path / "report.json"

    export_research_report(report, output)

    payload = json.loads(output.read_text())

    assert payload["schema_version"] == 2
    assert payload["datasets_duplicate"] == 1
    assert payload["total_valid_candles"] == 120
    assert payload["analysis_only"] is True
    assert (
        payload["directional_backtesting_allowed"]
        is False
    )
