
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from simulator.historical_integrity import (
    HistoricalProvenance,
    candles_available_at_signal_time,
    validate_historical_trade,
)


UTC = timezone.utc
START = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def make_candles(count=20):
    return pd.DataFrame([
        {
            "timestamp": START + timedelta(minutes=i),
            "Open": 100.0 + i,
            "High": 102.0 + i,
            "Low": 99.0 + i,
            "Close": 100.5 + i,
        }
        for i in range(count)
    ])


def provenance(
    feed_mode="regular",
    retrieved_minutes=20,
):
    return HistoricalProvenance(
        provider="TEST_PROVIDER",
        feed_mode=feed_mode,
        retrieved_at=START + timedelta(
            minutes=retrieved_minutes
        ),
    )


def test_valid_five_minute_historical_trade():
    result = validate_historical_trade(
        candles=make_candles(),
        entry_time=START,
        expiry_minutes=5,
        provenance=provenance(),
        claimed_entry_price=100.0,
    )

    assert result.entry_price == pytest.approx(100)
    assert result.expiry_price == pytest.approx(104.5)
    assert result.candle_count == 5
    assert result.expiry_time == START + timedelta(minutes=5)
    assert result.classification == "HISTORICAL_RESEARCH"


def test_valid_fifteen_minute_historical_trade():
    result = validate_historical_trade(
        candles=make_candles(),
        entry_time=START,
        expiry_minutes=15,
        provenance=provenance(),
    )

    assert result.candle_count == 15
    assert result.expiry_price == pytest.approx(114.5)


def test_missing_interval_candle_rejected():
    candles = make_candles().drop(index=3)

    with pytest.raises(ValueError, match="Missing"):
        validate_historical_trade(
            candles=candles,
            entry_time=START,
            expiry_minutes=5,
            provenance=provenance(),
        )


def test_mismatched_entry_price_rejected():
    with pytest.raises(ValueError, match="entry price"):
        validate_historical_trade(
            candles=make_candles(),
            entry_time=START,
            expiry_minutes=5,
            provenance=provenance(),
            claimed_entry_price=999.0,
        )


def test_unknown_feed_mode_rejected():
    with pytest.raises(ValueError, match="Unknown feed"):
        validate_historical_trade(
            candles=make_candles(),
            entry_time=START,
            expiry_minutes=5,
            provenance=provenance(feed_mode="unknown"),
        )


def test_incomplete_interval_rejected():
    with pytest.raises(ValueError, match="not fully completed"):
        validate_historical_trade(
            candles=make_candles(),
            entry_time=START,
            expiry_minutes=5,
            provenance=provenance(retrieved_minutes=4),
        )


def test_duplicate_candle_rejected():
    candles = make_candles()
    candles = pd.concat(
        [candles, candles.iloc[[2]]],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="Duplicate"):
        validate_historical_trade(
            candles=candles,
            entry_time=START,
            expiry_minutes=5,
            provenance=provenance(),
        )


def test_lookahead_candles_excluded():
    candles = make_candles()

    completed = candles_available_at_signal_time(
        candles=candles,
        signal_time=START + timedelta(minutes=5),
    )

    assert len(completed) == 5
    assert completed["timestamp"].max() == (
        START + timedelta(minutes=4)
    )


def test_naive_candle_timestamp_rejected():
    candles = make_candles()
    candles["timestamp"] = (
        candles["timestamp"].dt.tz_localize(None)
    )

    with pytest.raises(ValueError, match="timezone"):
        validate_historical_trade(
            candles=candles,
            entry_time=START,
            expiry_minutes=5,
            provenance=provenance(),
        )


def test_invalid_ohlc_rejected():
    candles = make_candles()
    candles.loc[2, "High"] = 90.0

    with pytest.raises(ValueError, match="OHLC"):
        validate_historical_trade(
            candles=candles,
            entry_time=START,
            expiry_minutes=5,
            provenance=provenance(),
        )

