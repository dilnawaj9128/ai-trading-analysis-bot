import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_guard import (
    ProviderCreditLimitReached,
    ProviderCreditStatusUnknown,
    check_provider_credits,
)


def snapshot(left):
    return CreditSnapshot(
        credits_used=None,
        credits_left=left,
        low_credits=False,
        information_available=left is not None,
    )


def test_sufficient_credits():
    result = check_provider_credits(snapshot(100))

    assert result.allowed is True
    assert result.remaining == 100


def test_low_credits_blocked():
    with pytest.raises(ProviderCreditLimitReached):
        check_provider_credits(snapshot(10))


def test_exact_reserve_boundary():
    result = check_provider_credits(snapshot(21))

    assert result.allowed is True


def test_below_reserve_boundary():
    with pytest.raises(ProviderCreditLimitReached):
        check_provider_credits(snapshot(20))


def test_unknown_credits_blocked():
    with pytest.raises(ProviderCreditStatusUnknown):
        check_provider_credits(snapshot(None))


def test_unknown_credits_explicitly_allowed():
    result = check_provider_credits(
        snapshot(None),
        allow_unknown=True,
    )

    assert result.allowed is True
    assert result.remaining is None


def test_custom_required_credits():
    with pytest.raises(ProviderCreditLimitReached):
        check_provider_credits(
            snapshot(25),
            required_credits=10,
        )


@pytest.mark.parametrize(
    "required,reserve",
    [
        (0, 20),
        (True, 20),
        (1, -1),
        (1, True),
    ],
)
def test_invalid_limits(required, reserve):
    with pytest.raises(ValueError):
        check_provider_credits(
            snapshot(100),
            required_credits=required,
            reserve_credits=reserve,
        )
