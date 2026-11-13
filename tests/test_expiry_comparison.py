
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import simulator.backtesting as bt

from data.historical_csv import load_historical_csv
from simulator.expiry_comparison import compare_expiries
from simulator.historical_integrity import HistoricalProvenance


UTC = timezone.utc
START = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def make_data(count=90):
    return pd.DataFrame([
        {
            "timestamp": (
                START + timedelta(minutes=i)
            ).isoformat(),
            "Open": 100 + i * 0.01,
            "High": 100.1 + i * 0.01,
            "Low": 99.9 + i * 0.01,
            "Close": 100.005 + i * 0.01,
        }
        for i in range(count)
    ])


def save_csv(tmp_path, data=None):
    path = tmp_path / "historical.csv"
    if data is None:
        data = make_data()
    data.to_csv(path, index=False)
    return path


def metadata(mode="live", minutes=100):
    # Test fixture only; not authenticated provenance.
    return HistoricalProvenance(
        provider="SYNTHETIC_TEST",
        feed_mode=mode,
        retrieved_at=START + timedelta(minutes=minutes),
    )


def test_valid_csv_loads(tmp_path):
    dataset = load_historical_csv(save_csv(tmp_path))

    assert dataset.candle_count == 90
    assert dataset.start_time == START
    assert dataset.end_time == (
        START + timedelta(minutes=89)
    )


def test_missing_column_rejected(tmp_path):
    data = make_data().drop(columns=["High"])

    with pytest.raises(ValueError, match="Missing"):
        load_historical_csv(save_csv(tmp_path, data))


def test_duplicate_candle_rejected(tmp_path):
    data = make_data()
    data.loc[10, "timestamp"] = data.loc[9, "timestamp"]

    with pytest.raises(ValueError):
        load_historical_csv(save_csv(tmp_path, data))


def test_missing_minute_rejected(tmp_path):
    data = make_data().drop(index=10)

    with pytest.raises(ValueError, match="missing minute"):
        load_historical_csv(save_csv(tmp_path, data))


def test_naive_timestamps_rejected(tmp_path):
    data = make_data()
    data["timestamp"] = data["timestamp"].str.replace(
        "+00:00", "", regex=False
    )

    with pytest.raises(ValueError):
        load_historical_csv(save_csv(tmp_path, data))


def test_unknown_feed_rejected(tmp_path):
    with pytest.raises(ValueError):
        compare_expiries(
            save_csv(tmp_path),
            metadata("unknown"),
        )


def test_early_retrieval_rejected(tmp_path):
    with pytest.raises(ValueError, match="retrieved_at"):
        compare_expiries(
            save_csv(tmp_path),
            metadata(minutes=80),
        )


def test_three_expiries_compared(tmp_path, monkeypatch):
    # Force a deterministic signal to test comparison
    # mechanics, not predictive strategy accuracy.
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

    comparison = compare_expiries(
        save_csv(tmp_path),
        metadata(),
    )

    assert set(comparison.reports) == {1, 5, 15}

    assert len(comparison.reports[1].trades) == 40
    assert len(comparison.reports[5].trades) == 8
    assert len(comparison.reports[15].trades) == 2

    assert comparison.reports[1].wins == 40
    assert comparison.reports[5].wins == 8
    assert comparison.reports[15].wins == 2

    assert comparison.reports[1].total_pnl == pytest.approx(1600)
    assert comparison.reports[5].total_pnl == pytest.approx(320)
    assert comparison.reports[15].total_pnl == pytest.approx(80)


def test_comparison_does_not_touch_paper_database(
    tmp_path, monkeypatch
):
    from database.repository import PaperTradingRepository

    db = tmp_path / "paper.db"
    repo = PaperTradingRepository(db)
    repo.get_or_create_account(10000.0)

    before_balance = repo.get_balance()
    before_trades = len(repo.get_all_trades())

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

    comparison = compare_expiries(
        save_csv(tmp_path),
        metadata(),
    )

    assert len(comparison.reports) == 3
    assert repo.get_balance() == before_balance
    assert len(repo.get_all_trades()) == before_trades

