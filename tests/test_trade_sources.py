
from datetime import datetime, timedelta, timezone

import pytest

from database.repository import PaperTradingRepository
from simulator.paper_trading import PaperTradingSimulator


def test_source_metadata_persists(tmp_path):
    repo = PaperTradingRepository(
        tmp_path / "paper.db"
    )

    simulator = PaperTradingSimulator(
        repository=repo
    )

    entry_time = datetime.now(timezone.utc)

    trade = simulator.open_trade(
        signal="UP",
        entry_price=100,
        stake=50,
        expiry_minutes=5,
        entry_time=entry_time,
    )

    simulator.settle_trade(
        trade_id=trade.trade_id,
        exit_price=101,
        exit_time=entry_time + timedelta(minutes=5),
    )

    restarted = PaperTradingSimulator(
        repository=repo
    )

    saved = restarted.trades[0]

    assert saved.trade_source == "MANUAL_TEST"
    assert saved.price_source == "MANUAL_INPUT"
    assert saved.expiry_price_time is None
    assert saved.result == "WIN"
    assert restarted.balance == pytest.approx(10040)


def test_unverified_market_source_rejected():
    simulator = PaperTradingSimulator()

    with pytest.raises(ValueError):
        simulator.open_trade(
            signal="UP",
            entry_price=100,
            stake=50,
            expiry_minutes=5,
            entry_time=datetime.now(timezone.utc),
            trade_source="MARKET_DATA",
        )


def test_manual_settlement_cannot_claim_verified_price():
    simulator = PaperTradingSimulator()

    entry_time = datetime.now(timezone.utc)

    trade = simulator.open_trade(
        signal="UP",
        entry_price=100,
        stake=50,
        expiry_minutes=5,
        entry_time=entry_time,
    )

    with pytest.raises(ValueError):
        simulator.settle_trade(
            trade_id=trade.trade_id,
            exit_price=101,
            exit_time=entry_time + timedelta(minutes=5),
            price_source="MARKET_DATA",
        )

    assert trade.status == "OPEN"
    assert simulator.balance == 9950

