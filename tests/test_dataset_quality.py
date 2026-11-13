
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from data.dataset_quality import audit_dataset


START = datetime(
    2026, 11, 12, 10, 0,
    tzinfo=timezone.utc,
)

def make_dataset(tmp_path, count=120):
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "eurusd_1min_utc.csv"
    receipt_path = tmp_path / "acquisition.json"

    frame = pd.DataFrame([
        {
            "timestamp": (
                START + timedelta(minutes=i)
            ).isoformat(),
            "Open": 1.1000,
            "High": 1.1005,
            "Low": 1.0995,
            "Close": 1.1002,
        }
        for i in range(count)
    ])

    frame.to_csv(csv_path, index=False)

    receipt = {
        "provider": "Twelve Data",
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "requested_timezone": "UTC",
        "timestamp_semantics": "candle_open_utc",
        "requested_start": START.isoformat(),
        "requested_end": (
            START + timedelta(minutes=count)
        ).isoformat(),
        "retrieved_at": (
            START + timedelta(minutes=count + 5)
        ).isoformat(),
        "candle_count": count,
        "csv_sha256": hashlib.sha256(
            csv_path.read_bytes()
        ).hexdigest(),
        "feed_mode": "unknown",
        "provider_feed_mode_verified": False,
        "broker_verified": False,
        "research_only": True,
    }

    receipt_path.write_text(json.dumps(receipt))

    return csv_path, receipt_path


def update_hash(csv_path, receipt_path):
    receipt = json.loads(receipt_path.read_text())
    receipt["csv_sha256"] = hashlib.sha256(
        csv_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt))


def test_valid_dataset_passes(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    report = audit_dataset(csv_path, receipt_path)

    assert report["status"] == "PASS"
    assert report["structural_integrity"] is True
    assert report["directional_backtesting_allowed"] is False
    assert report["metrics"]["candle_count"] == 120


def test_tampered_csv_fails(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    with csv_path.open("a") as file:
        file.write("\n")

    report = audit_dataset(csv_path, receipt_path)

    assert report["status"] == "FAIL"
    assert "CSV SHA-256 mismatch" in report["errors"]


def test_duplicate_timestamp_fails(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    frame = pd.read_csv(csv_path)
    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    frame.to_csv(csv_path, index=False)

    update_hash(csv_path, receipt_path)

    report = audit_dataset(csv_path, receipt_path)

    assert report["status"] == "FAIL"
    assert report["metrics"]["duplicate_count"] == 1


def test_invalid_ohlc_fails(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    frame = pd.read_csv(csv_path)
    frame.loc[0, "High"] = 1.0000
    frame.to_csv(csv_path, index=False)

    update_hash(csv_path, receipt_path)

    report = audit_dataset(csv_path, receipt_path)

    assert report["status"] == "FAIL"
    assert report["metrics"]["invalid_ohlc_count"] == 1


def test_missing_candle_fails(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    frame = pd.read_csv(csv_path)
    frame = frame.drop(index=10)
    frame.to_csv(csv_path, index=False)

    update_hash(csv_path, receipt_path)

    report = audit_dataset(csv_path, receipt_path)

    assert report["status"] == "FAIL"
    assert report["metrics"]["gap_count"] == 1


def test_unknown_feed_remains_blocked(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    report = audit_dataset(csv_path, receipt_path)

    assert report["status"] == "PASS"
    assert report["directional_backtesting_allowed"] is False
    assert report["metrics"]["feed_mode"] == "unknown"

