import csv
from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_stage46_settlement_audit import (
    assess,
    expected_result,
    parse_trades,
)

START = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

COLUMNS = [
    "trade_id", "entry_time", "direction", "entry_price",
    "expiry_time", "exit_price", "partition", "result",
    "profit_loss",
]


def make_data(tmp_path, trade_specs=None):
    candles = tmp_path / "candles.csv"
    ledger = tmp_path / "trades.csv"

    prices = [round(1.1 + i * 0.0001, 6) for i in range(120)]

    with candles.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["timestamp", "open", "high", "low", "close"]
        )
        for i, price in enumerate(prices):
            writer.writerow([
                (START + timedelta(minutes=i)).isoformat(),
                price, price + 0.001,
                price - 0.001, price,
            ])

    if trade_specs is None:
        trade_specs = [
            (20, "UP", "TRAINING"),
            (50, "DOWN", "TRAINING"),
            (100, "UP", "HOLDOUT"),
        ]

    with ledger.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()

        for index, (entry, direction, partition) in enumerate(
            trade_specs, 1
        ):
            expiry = entry + 15
            outcome, pnl = expected_result(
                direction, prices[entry], prices[expiry], 0.8
            )
            writer.writerow({
                "trade_id": f"T{index}",
                "entry_time": (
                    START + timedelta(minutes=entry)
                ).isoformat(),
                "direction": direction,
                "entry_price": prices[entry],
                "expiry_time": (
                    START + timedelta(minutes=expiry)
                ).isoformat(),
                "exit_price": prices[expiry],
                "partition": partition,
                "result": outcome,
                "profit_loss": pnl,
            })

    return candles, ledger


def mutate_trade(path, field, value, row_index=0):
    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    rows[row_index][field] = value

    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def problems(result):
    return {
        code
        for entry in result["errors"]
        if isinstance(entry, dict)
        for code in entry["problems"]
    }


def test_reconciles_valid_trades(tmp_path):
    candles, ledger = make_data(tmp_path)
    result = assess(candles, ledger)

    assert result["status"] == "OFFLINE_RECONCILED"
    assert result["metrics"]["total_trades"] == 3
    assert result["metrics"]["wins"] == 2
    assert result["metrics"]["losses"] == 1
    assert result["metrics"]["net_units"] == pytest.approx(0.6)


def test_missing_ledger_fails_closed(tmp_path):
    candles, ledger = make_data(tmp_path)
    ledger.unlink()

    result = assess(candles, ledger)
    assert result["status"] == "BLOCKED"
    assert result["metrics"] is None
    assert "TRADE_LEDGER_NOT_PROVIDED" in result["errors"]


def test_empty_ledger_fails_closed(tmp_path):
    candles, ledger = make_data(tmp_path, [])
    result = assess(candles, ledger)

    assert "TRADE_LEDGER_EMPTY" in result["errors"]


def test_entry_price_mismatch(tmp_path):
    candles, ledger = make_data(tmp_path)
    mutate_trade(ledger, "entry_price", "1.5")

    result = assess(candles, ledger)
    assert "ENTRY_PRICE_MISMATCH" in problems(result)
    assert result["metrics"] is None


def test_exit_price_mismatch(tmp_path):
    candles, ledger = make_data(tmp_path)
    mutate_trade(ledger, "exit_price", "1.5")

    result = assess(candles, ledger)
    assert "EXIT_PRICE_MISMATCH" in problems(result)


def test_wrong_outcome_detected(tmp_path):
    candles, ledger = make_data(tmp_path)
    mutate_trade(ledger, "result", "LOSS")

    result = assess(candles, ledger)
    assert "RECORDED_OUTCOME_MISMATCH" in problems(result)


def test_wrong_profit_detected(tmp_path):
    candles, ledger = make_data(tmp_path)
    mutate_trade(ledger, "profit_loss", "5")

    result = assess(candles, ledger)
    assert "RECORDED_PNL_MISMATCH" in problems(result)


def test_overlapping_trades_detected(tmp_path):
    candles, ledger = make_data(
        tmp_path,
        [(20, "UP", "TRAINING"),
         (30, "UP", "TRAINING")],
    )

    result = assess(candles, ledger)
    assert "OVERLAPPING_TRADES" in problems(result)


def test_training_settlement_leakage(tmp_path):
    candles, ledger = make_data(
        tmp_path, [(90, "UP", "TRAINING")]
    )

    result = assess(candles, ledger)
    assert "TRAINING_HOLDOUT_LEAKAGE" in problems(result)


def test_wrong_expiry_detected(tmp_path):
    candles, ledger = make_data(tmp_path)
    mutate_trade(
        ledger,
        "expiry_time",
        (START + timedelta(minutes=36)).isoformat(),
    )

    result = assess(candles, ledger)
    assert "WRONG_EXPIRY" in problems(result)


def test_direction_and_payout_math():
    assert expected_result("UP", 1.1, 1.2, 0.8) == (
        "WIN", 0.8
    )
    assert expected_result("DOWN", 1.1, 1.2, 0.8) == (
        "LOSS", -1.0
    )
    assert expected_result("UP", 1.1, 1.1, 0.8) == (
        "PUSH", 0.0
    )


def test_research_stays_unverified(tmp_path):
    candles, ledger = make_data(tmp_path)
    result = assess(candles, ledger)

    assert len(parse_trades(ledger)) == 3
    assert result["dataset_origin_verified"] is False
    assert result["forward_accuracy_proven"] is False
    assert result["directional_signals_authorized"] is False
    assert result["execution_enabled"] is False
    assert result["api_requests_executed"] == 0
