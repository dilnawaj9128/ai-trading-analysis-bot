import pandas as pd
import pytest

from market_data.session_batch_planner import plan_session_batches


def ts(value):
    return pd.Timestamp(value)


def test_weekday_batch():
    batches = plan_session_batches(
        "2026-11-12T10:00:00Z",
        "2026-11-12T10:10:00Z",
        batch_candles=10,
    )

    assert batches == [
        (
            ts("2026-11-12T10:00:00Z"),
            ts("2026-11-12T10:10:00Z"),
        )
    ]


def test_saturday_skipped():
    assert plan_session_batches(
        "2026-11-14T10:00:00Z",
        "2026-11-14T11:00:00Z",
    ) == []


def test_sunday_reopening():
    batches = plan_session_batches(
        "2026-11-15T21:30:00Z",
        "2026-11-15T22:30:00Z",
        batch_candles=60,
    )

    assert batches == [
        (
            ts("2026-11-15T22:00:00Z"),
            ts("2026-11-15T22:30:00Z"),
        )
    ]


def test_multiple_sessions():
    batches = plan_session_batches(
        "2026-11-13T21:00:00Z",
        "2026-11-15T23:00:00Z",
        batch_candles=60,
    )

    assert batches == [
        (
            ts("2026-11-13T21:00:00Z"),
            ts("2026-11-13T22:00:00Z"),
        ),
        (
            ts("2026-11-15T22:00:00Z"),
            ts("2026-11-15T23:00:00Z"),
        ),
    ]


def test_invalid_batch_size():
    with pytest.raises(ValueError, match="batch_candles"):
        plan_session_batches(
            "2026-11-12T10:00:00Z",
            "2026-11-12T11:00:00Z",
            batch_candles=0,
        )
