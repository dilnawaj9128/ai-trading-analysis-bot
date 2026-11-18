from datetime import datetime, timedelta, timezone

import pytest

from market_data.credit_refresh_lifecycle import (
    evaluate_refresh_lifecycle,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def evaluate(status=None, elapsed=None, **kwargs):
    attempt = (
        NOW - timedelta(seconds=elapsed)
        if elapsed is not None else None
    )

    return evaluate_refresh_lifecycle(
        last_attempt_at=attempt,
        last_status=status,
        now=NOW,
        **kwargs,
    )


def test_no_history_eligible():
    assert evaluate().action == "ELIGIBLE"


def test_claimed_blocks():
    assert evaluate("CLAIMED", 7200).action == "BLOCK"


def test_uncertain_blocks():
    assert evaluate("UNCERTAIN", 7200).action == "BLOCK"


def test_completed_inside_cooldown():
    assert evaluate("COMPLETED", 100).action == "COOLDOWN"


def test_completed_after_cooldown():
    assert evaluate("COMPLETED", 3600).action == "ELIGIBLE"


def test_future_timestamp_blocks():
    assert evaluate("COMPLETED", -10).action == "BLOCK"


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        evaluate("INVALID", 7200)


def test_incomplete_history_rejected():
    with pytest.raises(ValueError):
        evaluate("COMPLETED")
