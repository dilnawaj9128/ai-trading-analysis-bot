"""Independent Stage 50H audit of next-open historical research."""

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from research.stage29_backtest import load_candles
from research.stage50_next_open import (
    score_window,
    walk_forward_next_open,
)

CSV = Path("data/historical/eurusd_1min_1day.csv")
EXPECTED_SHA256 = (
    "92d48b2e1cea47b891b6b9df7b5b7f8871cb"
    "02051fb79f4ccbb62d694e40c6f8"
)


@pytest.fixture(scope="module")
def candles():
    assert CSV.is_file()
    digest = hashlib.sha256(CSV.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256

    data = load_candles(CSV)
    assert len(data) == 1440
    assert data.timestamp.diff().iloc[1:].eq(
        pd.Timedelta(minutes=1)
    ).all()
    return data


@pytest.fixture(scope="module")
def report(candles):
    return walk_forward_next_open(candles)


def test_real_dataset_strategy_selection(report):
    selections = [f["selected"] for f in report["folds"]]

    assert selections == [None, "rsi", "rsi", "rsi"]
    assert report["entry_model"] == "NEXT_CANDLE_OPEN"
    assert report["expiry_minutes"] == 15


def test_real_dataset_aggregate(report):
    stats = report["aggregate"]

    assert stats["signals"] == 20
    assert stats["wins"] == 8
    assert stats["losses"] == 10
    assert stats["pushes"] == 2
    assert stats["net_units"] == pytest.approx(-3.6)


def test_independent_trade_settlement(candles, report):
    audited = []

    for fold in report["folds"]:
        if fold["test"] is None:
            continue

        start = fold["test_start"]
        end = fold["test_end"]

        for trade in fold["test"]["trades"]:
            i = trade["signal_index"]
            entry_i = trade["entry_index"]
            exit_i = trade["expiry_index"]

            assert start <= i < end
            assert entry_i == i + 1
            assert exit_i == i + 15
            assert exit_i < end

            entry_time = candles.timestamp.iloc[entry_i]
            expiry_time = (
                candles.timestamp.iloc[exit_i]
                + pd.Timedelta(minutes=1)
            )

            assert expiry_time - entry_time == (
                pd.Timedelta(minutes=15)
            )

            entry = float(candles.Open.iloc[entry_i])
            exit_price = float(candles.Close.iloc[exit_i])

            assert trade["entry"] == pytest.approx(entry)
            assert trade["exit"] == pytest.approx(exit_price)

            if exit_price == entry:
                expected = "PUSH"
            elif trade["signal"] == "UP":
                expected = (
                    "WIN" if exit_price > entry else "LOSS"
                )
            elif trade["signal"] == "DOWN":
                expected = (
                    "WIN" if exit_price < entry else "LOSS"
                )
            else:
                pytest.fail("Unexpected signal")

            assert trade["result"] == expected
            audited.append(expected)

    assert len(audited) == 20
    assert audited.count("WIN") == 8
    assert audited.count("LOSS") == 10
    assert audited.count("PUSH") == 2


def test_nonoverlapping_trades(report):
    previous_expiry = -1

    for trade in report["test_trades"]:
        assert trade["entry_index"] >= previous_expiry
        previous_expiry = trade["expiry_index"]


def test_score_window_rejects_bad_payout(candles):
    def no_trade(_prefix):
        return "NO TRADE"

    with pytest.raises(ValueError):
        score_window(
            candles, no_trade, 59, 180, payout=0
        )
