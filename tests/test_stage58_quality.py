from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

from market_data.providers.data_quality_gate import (
    validate_live_frame,
)


def make_frame():
    start = datetime(
        2026, 11, 22, 10, 0,
        tzinfo=timezone.utc
    )

    rows = []

    for i in range(70):
        price = 1.1 + i * 0.00001

        rows.append({
            "timestamp": start + timedelta(minutes=i),
            "Open": price,
            "High": price + 0.0002,
            "Low": price - 0.0002,
            "Close": price + 0.00005,
        })

    return pd.DataFrame(rows)


def test_valid_live_frame():
    frame = make_frame()

    now = datetime(
        2026, 11, 22, 11, 10,
        tzinfo=timezone.utc
    )

    result = validate_live_frame(frame, now=now)

    assert result["quality"] == "VALID"
    assert result["feed_verified"] is False
    assert result["execution_enabled"] is False


def test_incomplete_candle_rejected():
    frame = make_frame()

    now = datetime(
        2026, 11, 22, 11, 9, 30,
        tzinfo=timezone.utc
    )

    with pytest.raises(ValueError):
        validate_live_frame(frame, now=now)


def test_stale_candles_rejected():
    frame = make_frame()

    now = datetime(
        2026, 11, 22, 12, 0,
        tzinfo=timezone.utc
    )

    with pytest.raises(ValueError):
        validate_live_frame(frame, now=now)


def test_missing_interval_rejected():
    frame = make_frame()
    frame = frame.drop(index=35).reset_index(drop=True)

    with pytest.raises(ValueError):
        validate_live_frame(
            frame,
            now=datetime(
                2026, 11, 22, 11, 10,
                tzinfo=timezone.utc
            ),
        )


def test_invalid_ohlc_rejected():
    frame = make_frame()
    frame.loc[5, "High"] = 0.5

    with pytest.raises(ValueError):
        validate_live_frame(
            frame,
            now=datetime(
                2026, 11, 22, 11, 10,
                tzinfo=timezone.utc
            ),
        )
