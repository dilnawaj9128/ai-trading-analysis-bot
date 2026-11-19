from datetime import datetime, timedelta, timezone

import pandas as pd

from scripts.run_stage46_walk_forward_audit import (
    audit_walk_forward,
)

START = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)


def sample():
    data = pd.DataFrame({
        "timestamp": [
            START + timedelta(minutes=i)
            for i in range(120)
        ],
        "Close": [1.1 + i * 0.0001 for i in range(120)],
    })

    trade = {
        "signal_index": 20,
        "expiry_index": 35,
        "signal_time": data["timestamp"].iloc[20].isoformat(),
        "signal": "UP",
        "entry": float(data["Close"].iloc[20]),
        "exit": float(data["Close"].iloc[35]),
        "result": "WIN",
    }

    report = {
        "folds": [{
            "test_start": 15,
            "test_end": 60,
            "selected": "rsi",
            "test": {"trades": [trade]},
        }],
        "test_trades": [trade],
    }
    return data, report


def error_codes(result):
    return {
        problem
        for error in result["errors"]
        for problem in error.get("problems", [error.get("problem")])
    }


def test_correct_settlement():
    data, report = sample()
    result = audit_walk_forward(data, report)

    assert result["status"] == "OFFLINE_RECONCILED"
    assert result["metrics"]["wins"] == 1
    assert result["metrics"]["net_units"] == 0.8


def test_modified_entry_rejected():
    data, report = sample()
    report["test_trades"][0]["entry"] += 0.01

    result = audit_walk_forward(data, report)

    assert "ENTRY_PRICE_MISMATCH" in error_codes(result)
    assert result["metrics"] is None


def test_modified_exit_rejected():
    data, report = sample()
    report["test_trades"][0]["exit"] += 0.01

    result = audit_walk_forward(data, report)

    assert "EXIT_PRICE_MISMATCH" in error_codes(result)


def test_expiry_index_rejected():
    data, report = sample()
    report["test_trades"][0]["expiry_index"] = 36

    result = audit_walk_forward(data, report)

    assert "WRONG_EXPIRY_INDEX" in error_codes(result)


def test_fold_boundary_rejected():
    data, report = sample()
    report["folds"][0]["test_end"] = 30

    result = audit_walk_forward(data, report)

    assert "FOLD_BOUNDARY_LEAKAGE" in error_codes(result)


def test_aggregate_missing_trade_rejected():
    data, report = sample()
    report["test_trades"] = []

    result = audit_walk_forward(data, report)

    assert "AGGREGATE_TRADE_LIST_MISMATCH" in error_codes(result)


def test_unverified_stays_unverified():
    data, report = sample()
    result = audit_walk_forward(data, report)

    assert result["dataset_origin_verified"] is False
    assert result["forward_accuracy_proven"] is False
