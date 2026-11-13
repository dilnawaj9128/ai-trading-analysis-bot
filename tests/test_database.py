from datetime import datetime, timedelta, timezone

from database.repository import PaperTradingRepository
from simulator import PaperTradingSimulator


def test_account_balance_persists_after_restart(tmp_path):
    db_path = tmp_path / "test.db"
    repository = PaperTradingRepository(str(db_path))

    simulator = PaperTradingSimulator(
        initial_balance=10000,
        repository=repository,
    )

    simulator.open_trade(
        "UP", 1.10, 100, 1,
        datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc),
    )

    restarted = PaperTradingSimulator(
        initial_balance=5000,
        repository=PaperTradingRepository(str(db_path)),
    )

    assert restarted.initial_balance == 10000
    assert restarted.balance == 9900
    assert len(restarted.trades) == 1
    assert restarted.trades[0].status == "OPEN"


def test_settled_trade_persists_after_restart(tmp_path):
    db_path = tmp_path / "test.db"
    repository = PaperTradingRepository(str(db_path))

    simulator = PaperTradingSimulator(repository=repository)
    entry_time = datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)

    trade = simulator.open_trade(
        "UP", 1.10, 100, 1, entry_time
    )

    simulator.settle_trade(
        trade.trade_id,
        1.11,
        entry_time + timedelta(minutes=1),
    )

    restarted = PaperTradingSimulator(
        repository=PaperTradingRepository(str(db_path))
    )

    assert restarted.balance == 10080
    assert len(restarted.trades) == 1
    assert restarted.trades[0].status == "CLOSED"
    assert restarted.trades[0].result == "WIN"
    assert restarted.trades[0].profit_loss == 80


def test_existing_account_is_not_reset(tmp_path):
    db_path = tmp_path / "test.db"

    first = PaperTradingSimulator(
        initial_balance=10000,
        repository=PaperTradingRepository(str(db_path)),
    )

    first.open_trade(
        "DOWN", 1.10, 200, 5,
        datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc),
    )

    second = PaperTradingSimulator(
        initial_balance=50000,
        repository=PaperTradingRepository(str(db_path)),
    )

    assert second.initial_balance == 10000
    assert second.balance == 9800
