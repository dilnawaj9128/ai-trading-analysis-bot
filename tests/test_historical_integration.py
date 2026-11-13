
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from database.repository import PaperTradingRepository
from simulator.paper_trading import PaperTradingSimulator


UTC = timezone.utc
START = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def make_candles():
    return pd.DataFrame([
        {
            "timestamp": START + timedelta(minutes=i),
            "Open": 100.0 + i,
            "High": 102.0 + i,
            "Low": 99.0 + i,
            "Close": 100.5 + i,
        }
        for i in range(10)
    ])


def open_research_trade(simulator):
    return simulator.open_trade(
        signal="UP",
        entry_price=100.0,
        stake=50.0,
        expiry_minutes=5,
        entry_time=START,
        trade_source="HISTORICAL_RESEARCH",
        data_quality_status="VALID",
    )


def test_historical_settlement_persists(tmp_path):
    repo = PaperTradingRepository(tmp_path / "paper.db")
    simulator = PaperTradingSimulator(repository=repo)

    trade = open_research_trade(simulator)

    result = simulator.settle_historical_trade(
        trade_id=trade.trade_id,
        candles=make_candles(),
        retrieved_at=START + timedelta(minutes=6),
    )

    assert result.result == "WIN"
    assert result.exit_price == pytest.approx(104.5)
    assert result.exit_time == START + timedelta(minutes=5)
    assert result.expiry_price_time == START + timedelta(minutes=4)
    assert result.price_source == "HISTORICAL_CANDLE"
    assert simulator.balance == pytest.approx(10040)

    restarted = PaperTradingSimulator(repository=repo)
    saved = restarted.trades[0]

    assert saved.trade_source == "HISTORICAL_RESEARCH"
    assert saved.price_source == "HISTORICAL_CANDLE"
    assert saved.expiry_price_time == START + timedelta(minutes=4)
    assert saved.result == "WIN"
    assert restarted.balance == pytest.approx(10040)


def test_manual_trade_cannot_use_historical_settlement():
    simulator = PaperTradingSimulator()

    trade = simulator.open_trade(
        signal="UP",
        entry_price=100,
        stake=50,
        expiry_minutes=5,
        entry_time=START,
    )

    with pytest.raises(ValueError):
        simulator.settle_historical_trade(
            trade_id=trade.trade_id,
            candles=make_candles(),
            retrieved_at=START + timedelta(minutes=6),
        )

    assert trade.status == "OPEN"
    assert simulator.balance == pytest.approx(9950)


def test_historical_trade_cannot_use_manual_settlement():
    simulator = PaperTradingSimulator()
    trade = open_research_trade(simulator)

    with pytest.raises(ValueError):
        simulator.settle_trade(
            trade_id=trade.trade_id,
            exit_price=105,
            exit_time=START + timedelta(minutes=6),
        )

    assert trade.status == "OPEN"
    assert simulator.balance == pytest.approx(9950)


def test_missing_candle_does_not_settle(tmp_path):
    repo = PaperTradingRepository(tmp_path / "paper.db")
    simulator = PaperTradingSimulator(repository=repo)

    trade = open_research_trade(simulator)

    candles = make_candles().drop(index=4)

    with pytest.raises(ValueError):
        simulator.settle_historical_trade(
            trade_id=trade.trade_id,
            candles=candles,
            retrieved_at=START + timedelta(minutes=6),
        )

    assert trade.status == "OPEN"
    assert simulator.balance == pytest.approx(9950)

    restarted = PaperTradingSimulator(repository=repo)

    assert restarted.trades[0].status == "OPEN"
    assert restarted.balance == pytest.approx(9950)


def test_duplicate_settlement_rejected():
    simulator = PaperTradingSimulator()

    trade = open_research_trade(simulator)

    simulator.settle_historical_trade(
        trade_id=trade.trade_id,
        candles=make_candles(),
        retrieved_at=START + timedelta(minutes=6),
    )

    with pytest.raises(ValueError):
        simulator.settle_historical_trade(
            trade_id=trade.trade_id,
            candles=make_candles(),
            retrieved_at=START + timedelta(minutes=6),
        )

    assert simulator.balance == pytest.approx(10040)

