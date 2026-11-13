from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import (
    load_credit_state,
    save_credit_state,
)
from market_data.credit_response_handler import (
    refresh_credits_from_response,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def response_with_credits(used, left):
    response = Mock()
    response.headers = {
        "api-credits-used": str(used),
        "api-credits-left": str(left),
    }
    return response


def test_older_response_cannot_overwrite_newer_snapshot(tmp_path):
    provider = tmp_path / "provider.json"

    newer_time = NOW + timedelta(seconds=10)

    refresh_credits_from_response(
        response_with_credits(10, 90),
        path=provider,
        now=newer_time,
    )

    refresh_credits_from_response(
        response_with_credits(5, 95),
        path=provider,
        now=NOW,
    )

    snapshot = load_credit_state(
        path=provider,
        now=newer_time,
    )

    assert snapshot.credits_left == 90
    assert snapshot.credits_used == 10


def test_equal_timestamp_cannot_increase_available_credits(tmp_path):
    provider = tmp_path / "provider.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=10,
            credits_left=90,
            low_credits=False,
            information_available=True,
        ),
        path=provider,
        now=NOW,
    )

    refresh_credits_from_response(
        response_with_credits(5, 95),
        path=provider,
        now=NOW,
    )

    snapshot = load_credit_state(
        path=provider,
        now=NOW,
    )

    assert snapshot.credits_left == 90


def test_newer_response_can_reduce_available_credits(tmp_path):
    provider = tmp_path / "provider.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=5,
            credits_left=95,
            low_credits=False,
            information_available=True,
        ),
        path=provider,
        now=NOW,
    )

    refresh_credits_from_response(
        response_with_credits(10, 90),
        path=provider,
        now=NOW + timedelta(seconds=10),
    )

    snapshot = load_credit_state(
        path=provider,
        now=NOW + timedelta(seconds=10),
    )

    assert snapshot.credits_left == 90
