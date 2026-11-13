from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from simulator.metrics import calculate_performance_metrics


@pytest.fixture
def sample_trades():
    start = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)

    return [
        SimpleNamespace(
            status="CLOSED",
            result="WIN",
            profit_loss=80.0,
            entry_time=start,
            exit_time=start + timedelta(minutes=1),
        ),
        SimpleNamespace(
            status="CLOSED",
            result="LOSS",
            profit_loss=-100.0,
            entry_time=start + timedelta(minutes=2),
            exit_time=start + timedelta(minutes=3),
        ),
        SimpleNamespace(
            status="CLOSED",
            result="PUSH",
            profit_loss=0.0,
            entry_time=start + timedelta(minutes=4),
            exit_time=start + timedelta(minutes=5),
        ),
        SimpleNamespace(
            status="OPEN",
            result=None,
            profit_loss=0.0,
            entry_time=start + timedelta(minutes=6),
            exit_time=None,
        ),
    ]


def test_trade_counts_and_win_rate(sample_trades):
    metrics = calculate_performance_metrics(sample_trades, 10000)

    assert metrics["total_trades"] == 4
    assert metrics["closed_trades"] == 3
    assert metrics["open_trades"] == 1
    assert metrics["wins"] == 1
    assert metrics["losses"] == 1
    assert metrics["pushes"] == 1
    assert metrics["decided_trades"] == 2
    assert metrics["win_rate_pct"] == pytest.approx(50)


def test_profit_loss_metrics(sample_trades):
    metrics = calculate_performance_metrics(sample_trades, 10000)

    assert metrics["total_profit_loss"] == pytest.approx(-20)
    assert metrics["average_profit_loss"] == pytest.approx(-20 / 3)
    assert metrics["ending_realized_balance"] == pytest.approx(9980)


def test_maximum_drawdown(sample_trades):
    metrics = calculate_performance_metrics(sample_trades, 10000)

    assert metrics["max_drawdown"] == pytest.approx(100)
    assert metrics["max_drawdown_pct"] == pytest.approx(100 / 10080 * 100)


def test_no_closed_trades():
    metrics = calculate_performance_metrics([], 10000)

    assert metrics["win_rate_pct"] == 0
    assert metrics["total_profit_loss"] == 0
    assert metrics["max_drawdown"] == 0
    assert metrics["closed_trades"] == 0


def test_invalid_initial_balance():
    with pytest.raises(ValueError):
        calculate_performance_metrics([], 0)
