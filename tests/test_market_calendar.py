import pandas as pd
import pytest

from market_data.market_calendar import is_full_saturday_utc


def test_saturday_window():
    assert is_full_saturday_utc(
        "2026-11-14T10:00:00Z",
        "2026-11-14T15:00:00Z",
    )


def test_weekday_window():
    assert not is_full_saturday_utc(
        "2026-11-13T10:00:00Z",
        "2026-11-13T15:00:00Z",
    )


def test_crossing_saturday_boundary():
    assert not is_full_saturday_utc(
        "2026-11-14T23:00:00Z",
        "2026-11-15T01:00:00Z",
    )


def test_invalid_window():
    with pytest.raises(ValueError):
        is_full_saturday_utc(
            "2026-11-14T15:00:00Z",
            "2026-11-14T10:00:00Z",
        )
