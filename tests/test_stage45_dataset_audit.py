import csv
from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_stage45_dataset_audit import (
    parse_candles,
    quality,
    split_safety,
    audit,
)

START = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


def make_csv(tmp_path, count=120, mutate=None):
    path = tmp_path / "candles.csv"
    rows = []

    for i in range(count):
        rows.append({
            "timestamp": (
                START + timedelta(minutes=i)
            ).isoformat(),
            "open": "1.10",
            "high": "1.20",
            "low": "1.00",
            "close": "1.15",
        })

    if mutate:
        mutate(rows)

    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "timestamp", "open", "high", "low", "close"
            ),
        )
        writer.writeheader()
        writer.writerows(rows)

    return path


def test_valid_contiguous_candles(tmp_path):
    path = make_csv(tmp_path)
    result = quality(parse_candles(path))
    assert result["rows"] == 120
    assert result["continuous_one_minute_candles"] is True


def test_duplicate_detected(tmp_path):
    def mutate(rows):
        rows[9]["timestamp"] = rows[8]["timestamp"]

    result = quality(parse_candles(make_csv(tmp_path, mutate=mutate)))
    assert result["duplicate_timestamps"] == 1
    assert result["continuous_one_minute_candles"] is False


def test_missing_minute_detected(tmp_path):
    def mutate(rows):
        for i in range(50, len(rows)):
            rows[i]["timestamp"] = (
                START + timedelta(minutes=i + 1)
            ).isoformat()

    result = quality(parse_candles(make_csv(tmp_path, mutate=mutate)))
    assert result["missing_minute_slots"] == 1


def test_backward_timestamp_detected(tmp_path):
    def mutate(rows):
        rows[20], rows[21] = rows[21], rows[20]

    result = quality(parse_candles(make_csv(tmp_path, mutate=mutate)))
    assert result["backward_timestamp_pairs"] >= 1


def test_invalid_ohlc_rejected(tmp_path):
    def mutate(rows):
        rows[4]["high"] = "0.50"

    with pytest.raises(ValueError, match="Inconsistent"):
        parse_candles(make_csv(tmp_path, mutate=mutate))


def test_nonfinite_price_rejected(tmp_path):
    def mutate(rows):
        rows[4]["close"] = "nan"

    with pytest.raises(ValueError, match="Nonpositive"):
        parse_candles(make_csv(tmp_path, mutate=mutate))


def test_naive_timestamp_rejected(tmp_path):
    def mutate(rows):
        rows[4]["timestamp"] = "2026-11-12T10:04:00"

    with pytest.raises(ValueError, match="Invalid row"):
        parse_candles(make_csv(tmp_path, mutate=mutate))


def test_training_settlement_does_not_cross_split(tmp_path):
    rows = parse_candles(make_csv(tmp_path))
    result = split_safety(rows)

    assert result["training_rows"] == 96
    assert result["holdout_rows"] == 24
    assert result["safe_training_entries"] == 81
    assert result["training_entries_excluded_at_boundary"] == 15
    assert result["safe_holdout_entries"] == 9


def test_short_dataset_fails_closed(tmp_path):
    rows = parse_candles(make_csv(tmp_path, count=20))
    result = split_safety(rows)
    assert result["status"] == "INSUFFICIENT_DATA"


def test_invalid_split_fraction_rejected(tmp_path):
    rows = parse_candles(make_csv(tmp_path))
    with pytest.raises(ValueError, match="fraction"):
        split_safety(rows, training_fraction=1.0)


def test_other_expiry_rejected(tmp_path):
    rows = parse_candles(make_csv(tmp_path))
    with pytest.raises(ValueError, match="15-minute"):
        split_safety(rows, expiry_minutes=5)


def test_audit_never_promotes_data_origin(tmp_path):
    result = audit(make_csv(tmp_path))
    assert result["research_status"] == "RESEARCH_ONLY"
    assert result["dataset_origin_verified"] is False
    assert result["forward_accuracy_proven"] is False
    assert result["api_requests_executed"] == 0
    assert result["execution_enabled"] is False
