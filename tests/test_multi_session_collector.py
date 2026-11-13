from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from market_data.resumable_collector import collect_resumable


def test_multi_session_collection(tmp_path):
    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

    start = pd.Timestamp("2026-11-13T21:00:00Z")
    end = pd.Timestamp("2026-11-15T23:00:00Z")

    calls = []

    def fake_fetch(config, *, start, end, **kwargs):
        calls.append((start, end))

        timestamps = pd.date_range(
            start=start,
            end=end,
            freq="min",
            inclusive="left",
        )

        return {
            "frame": pd.DataFrame({
                "timestamp": timestamps,
                "Open": 1.10,
                "High": 1.12,
                "Low": 1.09,
                "Close": 1.11,
            }),
            "possibly_truncated": False,
        }

    with patch(
        "market_data.resumable_collector.utc_now",
        return_value=pd.Timestamp("2026-11-17T12:00:00Z"),
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

    assert result["candles"] == 120
    assert result["new_requests"] == 2
    assert len(calls) == 2

    assert calls[0] == (
        pd.Timestamp("2026-11-13T21:00:00Z"),
        pd.Timestamp("2026-11-13T22:00:00Z"),
    )

    assert calls[1] == (
        pd.Timestamp("2026-11-15T22:00:00Z"),
        pd.Timestamp("2026-11-15T23:00:00Z"),
    )

    assert result["path"].exists()
