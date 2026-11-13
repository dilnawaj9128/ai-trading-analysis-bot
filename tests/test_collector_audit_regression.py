from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from market_data.resumable_collector import collect_resumable
from market_data.twelve_data_client import MarketDataError


def make_config():
    return SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )


def make_frame(start, end, missing=False):
    timestamps = pd.date_range(
        start=start,
        end=end,
        freq="min",
        inclusive="left",
    )

    if missing:
        timestamps = timestamps.delete(2)

    return pd.DataFrame({
        "timestamp": timestamps,
        "Open": 1.10,
        "High": 1.12,
        "Low": 1.09,
        "Close": 1.11,
    })


def run_collection(tmp_path, fetcher, max_requests=5):
    with patch(
        "market_data.resumable_collector.utc_now",
        return_value=pd.Timestamp(
            "2026-11-16T12:00:00Z"
        ),
    ), patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fetcher,
    ):
        return collect_resumable(
            make_config(),
            start=pd.Timestamp("2026-11-12T10:00:00Z"),
            end=pd.Timestamp("2026-11-12T10:10:00Z"),
            output_dir=tmp_path,
            batch_candles=10,
            max_requests=max_requests,
        )


def test_complete_data_saved(tmp_path):
    def fake_fetch(config, *, start, end, **kwargs):
        return {
            "frame": make_frame(start, end),
            "possibly_truncated": False,
        }

    result = run_collection(tmp_path, fake_fetch)

    assert result["candles"] == 10
    assert result["path"].exists()
    assert result["new_requests"] == 1


def test_missing_candle_rejected(tmp_path):
    def fake_fetch(config, *, start, end, **kwargs):
        return {
            "frame": make_frame(start, end, missing=True),
            "possibly_truncated": False,
        }

    with pytest.raises(MarketDataError, match="Incomplete batch"):
        run_collection(tmp_path, fake_fetch)

    assert not list(tmp_path.rglob("combined.csv"))


def test_request_limit_enforced(tmp_path):
    calls = []

    def fake_fetch(config, *, start, end, **kwargs):
        calls.append((start, end))
        return {
            "frame": make_frame(start, end),
            "possibly_truncated": False,
        }

    with patch(
        "market_data.resumable_collector.utc_now",
        return_value=pd.Timestamp("2026-11-16T12:00:00Z"),
    ), patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fake_fetch,
    ):
        with pytest.raises(
            MarketDataError,
            match="request budget exhausted",
        ):
            collect_resumable(
                make_config(),
                start=pd.Timestamp("2026-11-12T10:00:00Z"),
                end=pd.Timestamp("2026-11-12T10:20:00Z"),
                output_dir=tmp_path,
                batch_candles=10,
                max_requests=1,
            )

    assert len(calls) == 1
    assert len(list(tmp_path.rglob("batch_*.csv"))) == 1
    assert not list(tmp_path.rglob("combined.csv"))
