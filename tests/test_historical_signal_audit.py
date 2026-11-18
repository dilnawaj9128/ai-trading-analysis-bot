import pandas as pd
import pytest

from analysis.historical_signal_audit import (
    build_signal_audit_record,
    verify_signal_audit_record,
)


def sample_candles():
    return pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-11-12 10:00",
            periods=100,
            freq="min",
            tz="UTC",
        ),
        "Open": [1.10] * 100,
        "High": [1.20] * 100,
        "Low": [1.00] * 100,
        "Close": [1.10] * 100,
    })


def valid_audit():
    return {
        "status": "PASS",
        "metrics": {},
        "warnings": [],
    }


def make_record():
    return build_signal_audit_record(
        sample_candles(),
        selected_index=60,
        dataset_audit=valid_audit(),
    )


def test_unverified_feed_stays_no_trade():
    record = make_record()

    assert record["strategy_signal"] == "NO TRADE"
    assert record["comparison"] == "NOT_EVALUATED"
    assert record["provider_feed"] == "UNVERIFIED"
    assert record["broker_prices"] == "UNVERIFIED"


def test_audit_record_checksum_valid():
    assert verify_signal_audit_record(make_record())


def test_record_is_deterministic():
    first = make_record()
    second = make_record()

    assert first == second


def test_modified_record_detected():
    record = make_record()
    record["historical_outcome"] = "DOWN"

    assert not verify_signal_audit_record(record)


def test_failed_dataset_audit_blocks():
    with pytest.raises(ValueError):
        build_signal_audit_record(
            sample_candles(),
            selected_index=60,
            dataset_audit={
                "status": "FAIL",
                "metrics": {},
                "warnings": [],
            },
        )
