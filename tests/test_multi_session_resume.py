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


def test_resume_across_forex_sessions(tmp_path):
    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

    start = pd.Timestamp("2026-11-13T21:00:00Z")
    end = pd.Timestamp("2026-11-15T23:00:00Z")

    calls = []

    def fake_fetch(config, *, start, end, **kwargs):
        calls.append((start, end))

        if len(calls) == 2:
            raise MarketDataError("Simulated API interruption")

        return {
            "frame": make_frame(start, end),
            "possibly_truncated": False,
        }

    clock = patch(
        "market_data.resumable_collector.utc_now",
        return_value=pd.Timestamp("2026-11-17T12:00:00Z"),
    )

    fetch = patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fake_fetch,
    )

    with clock, fetch:
        with pytest.raises(
            MarketDataError,
            match="Simulated API interruption",
        ):
            collect_resumable(
                config,
                start=start,
                end=end,
                output_dir=tmp_path,
                batch_candles=60,
                max_requests=5,
            )

    # First batch must be saved before the interruption.
    assert len(list(tmp_path.rglob("batch_*.csv"))) == 1
    assert not list(tmp_path.rglob("combined.csv"))

    calls.clear()

    with clock, fetch:
        result = collect_resumable(
            config,
            start=start,
            end=end,
            output_dir=tmp_path,
            batch_candles=60,
            max_requests=5,
        )

    assert result["candles"] == 120
    assert result["cached_batches"] == 1
    assert result["new_requests"] == 1

    # Only the missing Sunday batch should be fetched.
    assert calls == [
        (
            pd.Timestamp("2026-11-15T22:00:00Z"),
            pd.Timestamp("2026-11-15T23:00:00Z"),
        )
    ]

    assert result["path"].exists()
