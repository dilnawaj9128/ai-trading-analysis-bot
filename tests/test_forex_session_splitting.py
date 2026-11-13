import pandas as pd
import pytest

from market_data.market_calendar import split_forex_open_windows


def ts(value):
    return pd.Timestamp(value)


def test_fully_open_window():
    result = split_forex_open_windows(
        "2026-11-12T10:00:00Z",
        "2026-11-12T11:00:00Z",
    )
    assert result == [
        (
            ts("2026-11-12T10:00:00Z"),
            ts("2026-11-12T11:00:00Z"),
        )
    ]


def test_fully_closed_saturday():
    assert split_forex_open_windows(
        "2026-11-14T10:00:00Z",
        "2026-11-14T11:00:00Z",
    ) == []


def test_sunday_reopening():
    result = split_forex_open_windows(
        "2026-11-15T21:30:00Z",
        "2026-11-15T22:30:00Z",
    )
    assert result == [
        (
            ts("2026-11-15T22:00:00Z"),
            ts("2026-11-15T22:30:00Z"),
        )
    ]


def test_friday_closing():
    result = split_forex_open_windows(
        "2026-11-13T21:30:00Z",
        "2026-11-13T22:30:00Z",
    )
    assert result == [
        (
            ts("2026-11-13T21:30:00Z"),
            ts("2026-11-13T22:00:00Z"),
        )
    ]


def test_summer_dst_reopening():
    result = split_forex_open_windows(
        "2026-07-12T20:30:00Z",
        "2026-07-12T21:30:00Z",
    )
    assert result == [
        (
            ts("2026-07-12T21:00:00Z"),
            ts("2026-07-12T21:30:00Z"),
        )
    ]


def test_unaligned_window_rejected():
    with pytest.raises(ValueError, match="align"):
        split_forex_open_windows(
            "2026-11-12T10:00:30Z",
            "2026-11-12T11:00:00Z",
        )
