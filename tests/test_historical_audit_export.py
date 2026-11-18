"""Stage 19L: offline export integration and fail-closed tests."""
import copy
import io
import json

import pandas as pd
import pytest

from analysis.historical_audit_export import build_audit_exports
from analysis.historical_signal_audit import verify_signal_audit_record


def candles():
    timestamps = pd.date_range(
        "2026-11-12T10:00:00Z", periods=120, freq="min", tz="UTC"
    )
    return pd.DataFrame({
        "timestamp": timestamps,
        "Open": [1.10] * 120,
        "High": [1.20] * 120,
        "Low": [1.00] * 120,
        "Close": [1.10] * 120,
    })


def passed_audit():
    return {"status": "PASS", "metrics": {}, "warnings": []}


def test_batch_has_four_records_with_valid_checksums():
    bundle = build_audit_exports(candles(), dataset_audit=passed_audit())
    assert bundle["record_count"] == 4
    assert all(verify_signal_audit_record(r) for r in bundle["records"])
    assert all(r["strategy_signal"] == "NO TRADE" for r in bundle["records"])


def test_csv_and_json_exports_are_consistent():
    bundle = build_audit_exports(candles(), dataset_audit=passed_audit())
    rows = pd.read_csv(io.BytesIO(bundle["csv_bytes"]))
    records = json.loads(bundle["json_bytes"].decode("utf-8"))
    assert len(rows) == len(records) == 4
    assert rows["record_sha256"].tolist() == [r["record_sha256"] for r in records]
    assert json.loads(rows.iloc[0]["reasons"]) == records[0]["reasons"]


def test_dataset_change_updates_outcomes_and_checksums():
    original = build_audit_exports(candles(), dataset_audit=passed_audit())
    changed_frame = candles()
    changed_frame.loc[74, "Close"] = 1.15
    changed = build_audit_exports(changed_frame, dataset_audit=passed_audit())
    assert original["records"][0]["historical_outcome"] == "FLAT"
    assert changed["records"][0]["historical_outcome"] == "UP"
    assert original["records"][0]["record_sha256"] != changed["records"][0]["record_sha256"]


def test_failed_dataset_audit_rejected():
    with pytest.raises(ValueError, match="PASS"):
        build_audit_exports(candles(), dataset_audit={"status": "FAIL"})


def test_missing_candle_rejected_without_partial_export():
    frame = candles()
    frame.loc[65, "timestamp"] += pd.Timedelta(minutes=3)
    with pytest.raises(ValueError):
        build_audit_exports(frame, dataset_audit=passed_audit())


def test_insufficient_candles_rejected():
    with pytest.raises(ValueError):
        build_audit_exports(candles().iloc[:74], dataset_audit=passed_audit())


def test_invalid_step_rejected():
    with pytest.raises(ValueError):
        build_audit_exports(candles(), dataset_audit=passed_audit(), step=1)


def test_repeated_exports_are_deterministic():
    a = build_audit_exports(candles(), dataset_audit=passed_audit())
    b = build_audit_exports(candles(), dataset_audit=passed_audit())
    assert a["csv_bytes"] == b["csv_bytes"]
    assert a["json_bytes"] == b["json_bytes"]
