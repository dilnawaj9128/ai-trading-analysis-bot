import pytest

from market_data.market_calendar import is_full_saturday_utc


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (
            "2026-11-14T10:00:00Z",
            "2026-11-14T11:00:00Z",
            True,
        ),
        (
            "2026-11-13T20:00:00Z",
            "2026-11-13T21:00:00Z",
            False,
        ),
        (
            "2026-11-13T23:00:00Z",
            "2026-11-14T01:00:00Z",
            False,
        ),
        (
            "2026-11-15T10:00:00Z",
            "2026-11-15T11:00:00Z",
            False,
        ),
        (
            "2026-11-15T23:00:00Z",
            "2026-11-16T00:00:00Z",
            False,
        ),
    ],
)
def test_conservative_saturday_classifier(start, end, expected):
    assert is_full_saturday_utc(start, end) is expected
