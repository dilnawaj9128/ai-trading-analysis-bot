import pytest

from market_data.market_calendar import (
    is_forex_market_open,
    is_full_forex_closure,
)


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        # Winter: NY is UTC-5.
        ("2026-11-15T21:59:00Z", False),
        ("2026-11-15T22:00:00Z", True),
        ("2026-11-20T21:59:00Z", True),
        ("2026-11-20T22:00:00Z", False),

        # Summer: NY is UTC-4.
        ("2026-07-12T20:59:00Z", False),
        ("2026-07-12T21:00:00Z", True),
        ("2026-07-17T20:59:00Z", True),
        ("2026-07-17T21:00:00Z", False),
    ],
)
def test_dst_session_boundaries(timestamp, expected):
    assert is_forex_market_open(timestamp) is expected


def test_full_saturday_closure():
    assert is_full_forex_closure(
        "2026-11-14T10:00:00Z",
        "2026-11-14T11:00:00Z",
    )


def test_friday_evening_closure():
    assert is_full_forex_closure(
        "2026-11-13T23:00:00Z",
        "2026-11-14T00:00:00Z",
    )


def test_sunday_reopening():
    assert not is_full_forex_closure(
        "2026-11-15T22:00:00Z",
        "2026-11-15T23:00:00Z",
    )


def test_mixed_open_closed_window():
    assert not is_full_forex_closure(
        "2026-11-15T21:30:00Z",
        "2026-11-15T22:30:00Z",
    )
