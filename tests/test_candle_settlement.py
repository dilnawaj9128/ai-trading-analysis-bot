
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from simulator.candle_settlement import get_expiry_price


UTC = timezone.utc


def make_candles():
    start = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

    return pd.DataFrame([
        {
            "timestamp": start + timedelta(minutes=i),
            "Open": 1.1000,
            "High": 1.1020,
            "Low": 1.0990,
            "Close": 1.1000 + i * 0.0001,
        }
        for i in range(10)
    ])


def test_five_minute_expiry_price():
    start = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

    result = get_expiry_price(
        candles=make_candles(),
        entry_time=start,
        expiry_minutes=5,
        retrieved_at=start + timedelta(minutes=6),
    )

    assert result.price == pytest.approx(1.1004)
    assert result.candle_time == start + timedelta(minutes=4)
    assert result.expiry_time == start + timedelta(minutes=5)


def test_reject_incomplete_expiry():
    start = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

    with pytest.raises(ValueError):
        get_expiry_price(
            candles=make_candles(),
            entry_time=start,
            expiry_minutes=5,
            retrieved_at=start + timedelta(minutes=4),
        )


def test_reject_missing_expiry_candle():
    start = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

    candles = make_candles()
    candles = candles.drop(index=4)

    with pytest.raises(ValueError):
        get_expiry_price(
            candles=candles,
            entry_time=start,
            expiry_minutes=5,
            retrieved_at=start + timedelta(minutes=6),
        )


def test_reject_unaligned_entry():
    start = datetime(
        2026, 11, 12, 10, 0, 30, tzinfo=UTC
    )

    with pytest.raises(ValueError):
        get_expiry_price(
            candles=make_candles(),
            entry_time=start,
            expiry_minutes=5,
            retrieved_at=start + timedelta(minutes=6),
        )


def test_reject_duplicate_expiry_candle():
    start = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

    candles = make_candles()
    duplicate = candles.iloc[[4]]
    candles = pd.concat([candles, duplicate], ignore_index=True)

    with pytest.raises(ValueError):
        get_expiry_price(
            candles=candles,
            entry_time=start,
            expiry_minutes=5,
            retrieved_at=start + timedelta(minutes=6),
        )

