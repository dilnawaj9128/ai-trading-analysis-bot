import pandas as pd
import pytest

from market_data import historical_dataset_builder as builder


def test_batch_windows_do_not_overlap():
    start = pd.Timestamp('2026-01-01T00:00:00Z')
    end = pd.Timestamp('2026-01-01T01:00:00Z')
    windows = builder.plan_batches(start=start, end=end, interval='1min', batch_candles=20)
    assert len(windows) == 3
    assert windows == [
        (start, start + pd.Timedelta(minutes=20)),
        (start + pd.Timedelta(minutes=20), start + pd.Timedelta(minutes=40)),
        (start + pd.Timedelta(minutes=40), end),
    ]


def test_invalid_batch_size_rejected():
    with pytest.raises(ValueError):
        builder.plan_batches(start='2026-01-01T00:00:00Z',
                             end='2026-01-01T01:00:00Z', interval='1min', batch_candles=0)


def test_unaligned_range_rejected():
    with pytest.raises(ValueError):
        builder.plan_batches(start='2026-01-01T00:00:30Z',
                             end='2026-01-01T01:00:00Z', interval='1min', batch_candles=20)


def test_request_limit_checked_before_fetch(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(builder, 'fetch_historical_candles', lambda *a, **k: calls.append(1))
    class Config:
        timeframe = '1min'
    with pytest.raises(ValueError, match='exceeds max_requests'):
        builder.collect_dataset(Config(), start='2026-01-01T00:00:00Z',
                                end='2026-01-01T01:00:00Z',
                                now='2026-01-02T00:00:00Z',
                                output_path=tmp_path / 'dataset.csv',
                                batch_candles=20, max_requests=2)
    assert not calls


def test_save_does_not_overwrite(tmp_path):
    frame = pd.DataFrame({
        'timestamp': pd.date_range('2026-01-01', periods=3, freq='min', tz='UTC'),
        'Open': [100., 101., 102.], 'High': [102., 103., 104.],
        'Low': [99., 100., 101.], 'Close': [101., 102., 103.],
    })
    path = tmp_path / 'history.csv'
    builder.save_historical_csv(frame, path)
    with pytest.raises(FileExistsError):
        builder.save_historical_csv(frame, path)
