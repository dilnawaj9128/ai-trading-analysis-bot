from datetime import datetime, timedelta, timezone

import pytest

from simulator import PaperTradingSimulator


@pytest.fixture
def simulator():
    return PaperTradingSimulator(initial_balance=10000)


@pytest.fixture
def entry_time():
    return datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)


def test_initial_balance(simulator):
    assert simulator.balance == 10000


def test_open_up_trade(simulator, entry_time):
    trade = simulator.open_trade(
        signal="UP",
        entry_price=1.10,
        stake=100,
        expiry_minutes=1,
        entry_time=entry_time,
    )

    assert trade.status == "OPEN"
    assert trade.direction == "UP"
    assert simulator.balance == 9900


def test_no_trade_signal_rejected(simulator, entry_time):
    with pytest.raises(ValueError):
        simulator.open_trade(
            "NO TRADE", 1.10, 100, 1, entry_time
        )


def test_invalid_data_rejected(simulator, entry_time):
    with pytest.raises(ValueError):
        simulator.open_trade(
            "UP", 1.10, 100, 1, entry_time,
            data_quality_status="STALE",
        )


def test_insufficient_balance_rejected(simulator, entry_time):
    with pytest.raises(ValueError):
        simulator.open_trade(
            "UP", 1.10, 20000, 1, entry_time
        )


def test_winning_up_trade(simulator, entry_time):
    trade = simulator.open_trade(
        "UP", 1.10, 100, 1, entry_time,
        payout_rate=0.80,
    )

    settled = simulator.settle_trade(
        trade.trade_id,
        exit_price=1.11,
        exit_time=entry_time + timedelta(minutes=1),
    )

    assert settled.result == "WIN"
    assert settled.profit_loss == pytest.approx(80)
    assert simulator.balance == pytest.approx(10080)


def test_losing_up_trade(simulator, entry_time):
    trade = simulator.open_trade(
        "UP", 1.10, 100, 1, entry_time
    )

    settled = simulator.settle_trade(
        trade.trade_id,
        exit_price=1.09,
        exit_time=entry_time + timedelta(minutes=1),
    )

    assert settled.result == "LOSS"
    assert settled.profit_loss == -100
    assert simulator.balance == 9900


def test_push_trade_returns_stake(simulator, entry_time):
    trade = simulator.open_trade(
        "UP", 1.10, 100, 1, entry_time
    )

    settled = simulator.settle_trade(
        trade.trade_id,
        exit_price=1.10,
        exit_time=entry_time + timedelta(minutes=1),
    )

    assert settled.result == "PUSH"
    assert settled.profit_loss == 0
    assert simulator.balance == pytest.approx(10000)


def test_early_settlement_rejected(simulator, entry_time):
    trade = simulator.open_trade(
        "UP", 1.10, 100, 5, entry_time
    )

    with pytest.raises(ValueError):
        simulator.settle_trade(
            trade.trade_id,
            1.11,
            entry_time + timedelta(minutes=2),
        )


def test_trade_cannot_be_settled_twice(simulator, entry_time):
    trade = simulator.open_trade(
        "UP", 1.10, 100, 1, entry_time
    )

    simulator.settle_trade(
        trade.trade_id,
        1.11,
        entry_time + timedelta(minutes=1),
    )

    with pytest.raises(ValueError):
        simulator.settle_trade(
            trade.trade_id,
            1.12,
            entry_time + timedelta(minutes=2),
        )
