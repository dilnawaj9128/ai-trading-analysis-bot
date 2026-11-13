from datetime import datetime, timedelta, timezone

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_guard import (
    ProviderCreditLimitReached,
    ProviderCreditStatusUnknown,
)
from market_data.provider_credit_state import save_credit_state
from market_data.pre_request_credit_gate import check_before_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def save_snapshot(tmp_path, left, observed_at=NOW):
    path = tmp_path / "provider.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=5,
            credits_left=left,
            low_credits=left < 20 if left is not None else False,
            information_available=left is not None,
        ),
        path=path,
        now=observed_at,
    )

    return path


def test_sufficient_credits(tmp_path):
    path = save_snapshot(tmp_path, 100)

    result = check_before_request(path=path, now=NOW)

    assert result.allowed is True
    assert result.remaining_credits == 100


def test_insufficient_credits(tmp_path):
    path = save_snapshot(tmp_path, 10)

    with pytest.raises(ProviderCreditLimitReached):
        check_before_request(path=path, now=NOW)


def test_missing_snapshot(tmp_path):
    with pytest.raises(ProviderCreditStatusUnknown):
        check_before_request(
            path=tmp_path / "missing.json",
            now=NOW,
        )


def test_expired_snapshot(tmp_path):
    path = save_snapshot(
        tmp_path,
        100,
        observed_at=NOW - timedelta(minutes=10),
    )

    with pytest.raises(ProviderCreditStatusUnknown):
        check_before_request(path=path, now=NOW)


def test_unknown_remaining_credits(tmp_path):
    path = save_snapshot(tmp_path, None)

    with pytest.raises(ProviderCreditStatusUnknown):
        check_before_request(path=path, now=NOW)


def test_exact_credit_boundary(tmp_path):
    path = save_snapshot(tmp_path, 21)

    result = check_before_request(path=path, now=NOW)

    assert result.allowed is True


def test_custom_credit_cost(tmp_path):
    path = save_snapshot(tmp_path, 25)

    with pytest.raises(ProviderCreditLimitReached):
        check_before_request(
            path=path,
            now=NOW,
            required_credits=10,
        )


def test_corrupted_state_rejected(tmp_path):
    path = tmp_path / "provider.json"
    path.write_text("{broken")

    with pytest.raises(ValueError):
        check_before_request(path=path, now=NOW)
