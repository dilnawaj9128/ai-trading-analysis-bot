from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_guard import (
    ProviderCreditLimitReached,
    ProviderCreditStatusUnknown,
)
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def make_state(tmp_path, left=100, observed_at=NOW):
    path = tmp_path / "provider.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=5,
            credits_left=left,
            low_credits=left is not None and left < 20,
            information_available=left is not None,
        ),
        path=path,
        now=observed_at,
    )

    return path


def test_authorized_request_reserves_budget(tmp_path):
    provider_path = make_state(tmp_path)

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        result = authorize_request(
            provider_state_path=provider_path,
            local_budget_path=tmp_path / "budget.json",
            now=NOW,
        )

    assert result.authorized is True
    assert result.local_budget_reserved is True
    assert result.provider_credits_remaining == 99
    reserve.assert_called_once()


def test_low_provider_credits_do_not_reserve(tmp_path):
    provider_path = make_state(tmp_path, left=10)

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(ProviderCreditLimitReached):
            authorize_request(
                provider_state_path=provider_path,
                now=NOW,
            )

    reserve.assert_not_called()


def test_missing_provider_state_do_not_reserve(tmp_path):
    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(ProviderCreditStatusUnknown):
            authorize_request(
                provider_state_path=tmp_path / "missing.json",
                now=NOW,
            )

    reserve.assert_not_called()


def test_expired_provider_state_do_not_reserve(tmp_path):
    provider_path = make_state(
        tmp_path,
        observed_at=NOW - timedelta(minutes=10),
    )

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(ProviderCreditStatusUnknown):
            authorize_request(
                provider_state_path=provider_path,
                now=NOW,
            )

    reserve.assert_not_called()


def test_local_budget_failure_propagates(tmp_path):
    provider_path = make_state(tmp_path)

    with patch(
        "market_data.unified_request_guard.reserve_request",
        side_effect=RuntimeError("Local budget unavailable"),
    ):
        with pytest.raises(RuntimeError, match="Local budget unavailable"):
            authorize_request(
                provider_state_path=provider_path,
                now=NOW,
            )


def test_exact_provider_credit_boundary(tmp_path):
    provider_path = make_state(tmp_path, left=21)

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ):
        result = authorize_request(
            provider_state_path=provider_path,
            now=NOW,
        )

    assert result.authorized is True


def test_custom_required_credits_blocked(tmp_path):
    provider_path = make_state(tmp_path, left=25)

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(ProviderCreditLimitReached):
            authorize_request(
                provider_state_path=provider_path,
                now=NOW,
                required_credits=10,
            )

    reserve.assert_not_called()
