from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from market_data.resumable_collector import collect_resumable
from market_data.twelve_data_client import MarketDataError


def make_frame(start, end):
    timestamps = pd.date_range(
        start=start,
        end=end,
        freq="min",
        inclusive="left",
    )

    return pd.DataFrame({
        "timestamp": timestamps,
        "Open": 1.10,
        "High": 1.12,
        "Low": 1.09,
        "Close": 1.11,
    })


def test_request_budget_stops_collection(tmp_path):
    calls = []

    def fake_fetch(config, *, start, end, **kwargs):
        calls.append((start, end))
        return {
            "frame": make_frame(start, end),
            "possibly_truncated": False,
        }

    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

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
                config,
                start=pd.Timestamp("2026-11-12T10:00:00Z"),
                end=pd.Timestamp("2026-11-12T10:30:00Z"),
                output_dir=tmp_path,
                batch_candles=10,
                max_requests=2,
            )

    assert len(calls) == 2
    assert len(list(tmp_path.rglob("batch_*.csv"))) == 2
    assert not list(tmp_path.rglob("combined.csv"))


def test_weekend_requires_no_api_requests(tmp_path):
    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

    with patch(
        "market_data.resumable_collector.utc_now",
        return_value=pd.Timestamp("2026-11-16T12:00:00Z"),
    ), patch(
        "market_data.resumable_collector.fetch_historical_candles",
    ) as fetch:
        with pytest.raises(
            MarketDataError,
            match="No trading candles collected",
        ):
            collect_resumable(
                config,
                start=pd.Timestamp("2026-11-14T10:00:00Z"),
                end=pd.Timestamp("2026-11-14T11:00:00Z"),
                output_dir=tmp_path,
                batch_candles=60,
                max_requests=2,
            )

    fetch.assert_not_called()
