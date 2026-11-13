from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from market_data.resumable_collector import collect_resumable


def test_sunday_mixed_session(tmp_path):
    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

    start = pd.Timestamp("2026-11-15 21:30", tz="UTC")
    end = pd.Timestamp("2026-11-15 22:30", tz="UTC")

    calls = []

    def fake_fetch(config, *, start, end, **kwargs):
        calls.append((start, end))

        timestamps = pd.date_range(
            start,
            end,
            freq="min",
            inclusive="left",
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
        "market_data.resumable_collector.utc_now",
        return_value=pd.Timestamp("2026-11-16 12:00", tz="UTC"),
    ), patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fake_fetch,
    ):
        result = collect_resumable(
            config,
            start=start,
            end=end,
            output_dir=tmp_path,
            batch_candles=60,
            max_requests=5,
        )

    assert result["candles"] == 30
    assert result["new_requests"] == 1

    assert calls == [
        (
            pd.Timestamp("2026-11-15 22:00", tz="UTC"),
            pd.Timestamp("2026-11-15 22:30", tz="UTC"),
        )
    ]
