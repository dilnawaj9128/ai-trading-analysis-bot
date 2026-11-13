from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from market_data.resumable_collector import collect_resumable


def test_collector_returns_integrity_report(tmp_path):
    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

    start = pd.Timestamp("2026-11-12T10:00:00Z")
    end = pd.Timestamp("2026-11-12T10:10:00Z")

    def fake_fetch(config, *, start, end, **kwargs):
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
        return_value=pd.Timestamp("2026-11-16T12:00:00Z"),
    ), patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fake_fetch,
    ):
        result = collect_resumable(
            config,
            start=start,
            end=end,
            output_dir=tmp_path,
            batch_candles=10,
            max_requests=5,
        )

    assert result["audit"]["complete"] is True
    assert result["audit"]["actual_candles"] == 10
    assert result["audit"]["expected_open_candles"] == 10
    assert result["audit"]["missing_open_candles"] == 0
    assert result["audit"]["unexpected_closed_candles"] == 0
    assert result["path"].exists()
