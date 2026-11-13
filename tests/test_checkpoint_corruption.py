from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from market_data.resumable_collector import collect_resumable
from market_data.twelve_data_client import MarketDataError


START = pd.Timestamp("2026-11-12T10:00:00Z")
END = pd.Timestamp("2026-11-12T10:10:00Z")


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


def run_collector(tmp_path, fetcher):
    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
    )

    with patch(
        "market_data.resumable_collector.utc_now",
        return_value=pd.Timestamp("2026-11-16T12:00:00Z"),
    ), patch(
        "market_data.resumable_collector.fetch_historical_candles",
        side_effect=fetcher,
    ):
        return collect_resumable(
            config,
            start=START,
            end=END,
            output_dir=tmp_path,
            batch_candles=10,
            max_requests=5,
        )


@pytest.mark.parametrize(
    "corruption",
    [
        "missing",
        "duplicate",
        "invalid_ohlc",
        "outside_window",
    ],
)
def test_corrupted_checkpoint_rejected(tmp_path, corruption):
    def fake_fetch(config, *, start, end, **kwargs):
        return {
            "frame": make_frame(start, end),
            "possibly_truncated": False,
        }

    result = run_collector(tmp_path, fake_fetch)

    checkpoint = next(tmp_path.rglob("batch_*.csv"))
    frame = pd.read_csv(checkpoint)

    if corruption == "missing":
        frame = frame.drop(index=2)

    elif corruption == "duplicate":
        frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"]

    elif corruption == "invalid_ohlc":
        frame.loc[2, "High"] = 0.5

    elif corruption == "outside_window":
        frame.loc[2, "timestamp"] = "2026-11-13T10:00:00Z"

    frame.to_csv(checkpoint, index=False)

    def forbidden_fetch(*args, **kwargs):
        raise AssertionError(
            "Corrupted cache must not trigger an API request"
        )

    with pytest.raises(
        MarketDataError,
    ):
        run_collector(tmp_path, forbidden_fetch)

    # The previously generated combined.csv may exist.
    # Corrupted checkpoint must not be accepted as a valid resume.
    assert result["path"].exists()
