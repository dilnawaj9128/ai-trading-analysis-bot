from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from market_data.resumable_collector import collect_resumable
from market_data.twelve_data_client import MarketDataError


def test_resume_after_interruption(tmp_path):
    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

    start = pd.Timestamp("2026-11-12 10:00", tz="UTC")
    end = start + pd.Timedelta(minutes=6)

    calls = []

    def fake_fetch(config, *, start, end, **kwargs):
        calls.append((start, end))

        if len(calls) == 2:
            raise MarketDataError("Simulated API interruption")

        timestamps = pd.date_range(
            start,
            end - pd.Timedelta(minutes=1),
            freq="min",
            tz="UTC",
        )

        frame = pd.DataFrame({
            "timestamp": timestamps,
            "Open": 1.10,
            "High": 1.12,
            "Low": 1.09,
            "Close": 1.11,
        })

        return {
            "frame": frame,
            "possibly_truncated": False,
        }

    with patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fake_fetch,
    ):
        with pytest.raises(MarketDataError):
            collect_resumable(
                config,
                start=start,
                end=end,
                output_dir=tmp_path,
                batch_candles=3,
                max_requests=5,
            )

    # Resume: first successful batch should be reused.
    calls.clear()

    with patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fake_fetch,
    ):
        result = collect_resumable(
            config,
            start=start,
            end=end,
            output_dir=tmp_path,
            batch_candles=3,
            max_requests=5,
        )

    assert result["candles"] == 6
    assert result["cached_batches"] == 1
    assert result["new_requests"] == 1
    assert result["gaps"] == 0
