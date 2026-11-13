from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from market_data.historical_collector import parse_historical_payload, fetch_historical_candles, save_historical_csv
from market_data.twelve_data_client import MarketDataError

START = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, 10, 3, tzinfo=timezone.utc)
NOW = datetime(2026, 1, 1, 11, tzinfo=timezone.utc)


def payload(times=('2026-01-01 10:00:00', '2026-01-01 10:01:00')):
    return {'meta': {'symbol': 'EUR/USD', 'interval': '1min'}, 'values': [
        {'datetime': t, 'open': '1.1', 'high': '1.2', 'low': '1.0', 'close': '1.15'} for t in times
    ]}


def test_valid_historical_candles():
    frame = parse_historical_payload(payload(), symbol='EUR/USD', interval='1min', start=START, end=END, now=NOW)
    assert len(frame) == 2
    assert str(frame.iloc[0]['timestamp'].tzinfo) == 'UTC'


def test_reject_outside_window():
    with pytest.raises(MarketDataError, match='outside requested window'):
        parse_historical_payload(payload(('2026-01-01 10:03:00',)), symbol='EUR/USD', interval='1min', start=START, end=END, now=NOW)


def test_reject_duplicate():
    with pytest.raises(MarketDataError, match='Duplicate'):
        parse_historical_payload(payload(('2026-01-01 10:00:00', '2026-01-01 10:00:00')), symbol='EUR/USD', interval='1min', start=START, end=END, now=NOW)


def test_reject_incomplete():
    with pytest.raises(MarketDataError, match='Incomplete'):
        parse_historical_payload(payload(('2026-01-01 10:02:00',)), symbol='EUR/USD', interval='1min', start=START, end=END, now=datetime(2026, 1, 1, 10, 2, 30, tzinfo=timezone.utc))


def test_save_no_overwrite(tmp_path):
    frame = parse_historical_payload(payload(), symbol='EUR/USD', interval='1min', start=START, end=END, now=NOW)
    dest = tmp_path / 'candles.csv'
    save_historical_csv(frame, dest)
    assert len(pd.read_csv(dest)) == 2
    with pytest.raises(FileExistsError):
        save_historical_csv(frame, dest)
