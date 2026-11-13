
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import simulator.backtesting as bt
from simulator.historical_integrity import HistoricalProvenance


START = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


def candles(count=80):
    return pd.DataFrame([
        {
            "timestamp": START + timedelta(minutes=i),
            "Open": 100 + i * 0.01,
            "High": 100.1 + i * 0.01,
            "Low": 99.9 + i * 0.01,
            "Close": 100.005 + i * 0.01,
        }
        for i in range(count)
    ])


def provenance(mode="live"):
    # Synthetic metadata for unit tests only.
    # This does not verify a real provider.
    return HistoricalProvenance(
        provider="SYNTHETIC_TEST",
        feed_mode=mode,
        retrieved_at=START + timedelta(minutes=100),
    )


def test_unknown_feed_is_blocked():
    with pytest.raises(ValueError, match="verified"):
        bt.run_backtest(
            candles(), provenance("unknown")
        )


def test_missing_candle_is_blocked():
    data = candles().drop(index=10)

    with pytest.raises(ValueError, match="missing"):
        bt.run_backtest(data, provenance())


def test_no_trade_produces_no_positions(monkeypatch):
    monkeypatch.setattr(
        bt, "calculate_indicators", lambda data: data
    )
    monkeypatch.setattr(
        bt, "detect_candlestick_patterns", lambda data: data
    )
    monkeypatch.setattr(
        bt, "generate_signal",
        lambda *args, **kwargs: {"signal": "NO TRADE"},
    )

    report = bt.run_backtest(
        candles(), provenance(), expiry_minutes=5
    )

    assert len(report.trades) == 0
    assert report.total_pnl == 0
    assert report.no_trade_count == report.signals_checked


def test_completed_candles_only(monkeypatch):
    observed = []

    def indicators(data):
        observed.append(data.copy())
        return data

    monkeypatch.setattr(
        bt, "calculate_indicators", indicators
    )
    monkeypatch.setattr(
        bt, "detect_candlestick_patterns", lambda data: data
    )
    monkeypatch.setattr(
        bt, "generate_signal",
        lambda *args, **kwargs: {"signal": "NO TRADE"},
    )

    bt.run_backtest(
        candles(), provenance(), expiry_minutes=5
    )

    assert observed

    # First signal at minute 50 uses candles 0..49.
    assert len(observed[0]) == 50
    assert observed[0]["timestamp"].max() == (
        START + timedelta(minutes=49)
    )

    # No analysis call should contain its entry candle.
    for index, frame in enumerate(observed):
        entry = START + timedelta(minutes=50 + index)
        assert frame["timestamp"].max() < entry


def test_five_minute_settlement(monkeypatch):
    monkeypatch.setattr(
        bt, "calculate_indicators", lambda data: data
    )
    monkeypatch.setattr(
        bt, "detect_candlestick_patterns", lambda data: data
    )
    monkeypatch.setattr(
        bt, "generate_signal",
        lambda *args, **kwargs: {"signal": "UP"},
    )

    report = bt.run_backtest(
        candles(), provenance(), expiry_minutes=5
    )

    assert len(report.trades) == 6
    assert report.wins == 6
    assert report.losses == 0
    assert report.total_pnl == pytest.approx(240.0)

    first = report.trades[0]
    assert first.entry_time == START + timedelta(minutes=50)
    assert first.expiry_time == START + timedelta(minutes=55)
    assert first.entry_price == pytest.approx(100.50)
    assert first.expiry_price == pytest.approx(100.545)


def test_no_overlapping_positions(monkeypatch):
    monkeypatch.setattr(
        bt, "calculate_indicators", lambda data: data
    )
    monkeypatch.setattr(
        bt, "detect_candlestick_patterns", lambda data: data
    )
    monkeypatch.setattr(
        bt, "generate_signal",
        lambda *args, **kwargs: {"signal": "DOWN"},
    )

    report = bt.run_backtest(
        candles(), provenance(), expiry_minutes=15
    )

    assert len(report.trades) == 2
    assert report.losses == 2

    for previous, following in zip(
        report.trades, report.trades[1:]
    ):
        assert following.entry_time >= previous.expiry_time


def test_invalid_expiry_rejected():
    with pytest.raises(ValueError, match="Expiry"):
        bt.run_backtest(
            candles(), provenance(), expiry_minutes=10
        )


def test_invalid_stake_rejected():
    with pytest.raises(ValueError, match="Stake"):
        bt.run_backtest(
            candles(), provenance(), stake=-50
        )

