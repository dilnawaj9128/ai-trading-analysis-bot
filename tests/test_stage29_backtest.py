import pandas as pd
import pytest
from research.stage29_backtest import backtest, load_candles, BacktestDataError


def sample(n=240):
    ts = pd.date_range("2026-11-16 09:00", periods=n, freq="min", tz="UTC")
    price = [1.0 + i * 0.0001 for i in range(n)]
    return pd.DataFrame({"timestamp": ts, "Open": price,
                         "High": [v + 0.0002 for v in price],
                         "Low": [v - 0.0002 for v in price], "Close": price})


def test_only_prefix_reaches_signal_function():
    data = sample()
    ends = []
    def signal(prefix):
        ends.append(prefix.timestamp.iloc[-1])
        assert len(prefix) < len(data)
        return "UP"
    result = backtest(data, signal_fn=signal)
    assert result["holdout"]["wins"] > 0
    assert ends == sorted(ends)


def test_opposite_direction_loses():
    result = backtest(sample(), signal_fn=lambda _: "DOWN")
    assert result["holdout"]["wins"] == 0
    assert result["holdout"]["losses"] > 0


def test_no_trade_does_not_count_as_win():
    result = backtest(sample(), signal_fn=lambda _: "NO TRADE")
    assert result["holdout"]["win_rate"] is None
    assert result["holdout"]["signals"] == 0
    assert result["holdout"]["no_trade"] > 0


def test_gap_blocks_invalid_windows():
    data = sample()
    data.loc[130:, "timestamp"] += pd.Timedelta(minutes=5)
    result = backtest(data, signal_fn=lambda _: "UP")
    assert result["training"]["skipped_windows"] + result["holdout"]["skipped_windows"] > 0


def test_expiry_rejected():
    with pytest.raises(ValueError):
        backtest(sample(), expiry=5)


def test_csv_requires_timezone(tmp_path):
    path = tmp_path / "bad.csv"
    data = sample()
    data["timestamp"] = data["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    data.to_csv(path, index=False)
    with pytest.raises(BacktestDataError, match="offset"):
        load_candles(path)


def test_no_cross_boundary_training_outcome():
    result = backtest(sample(), signal_fn=lambda _: "UP")
    train_exits = [t for t in result['trades'] if t['partition'] == 'training']
    holdout_entries = [t for t in result['trades'] if t['partition'] == 'holdout']
    assert train_exits and holdout_entries
    assert train_exits[-1]['exit_time_utc'] <= holdout_entries[0]['entry_time_utc']
