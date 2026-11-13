"""Provider credit guard for research-only data acquisition.

No API calls are performed by this module.
"""

from dataclasses import dataclass

from market_data.api_credit_monitor import CreditSnapshot


class ProviderCreditLimitReached(Exception):
    """Provider reports insufficient remaining credits."""


class ProviderCreditStatusUnknown(Exception):
    """Provider credit information is unavailable."""


@dataclass(frozen=True)
class CreditDecision:
    allowed: bool
    remaining: int | None
    reason: str


def check_provider_credits(
    snapshot: CreditSnapshot,
    *,
    required_credits: int = 1,
    reserve_credits: int = 20,
    allow_unknown: bool = False,
) -> CreditDecision:

    if not isinstance(snapshot, CreditSnapshot):
        raise ValueError("CreditSnapshot required")

    if type(required_credits) is not int or required_credits < 1:
        raise ValueError("Invalid required_credits")

    if type(reserve_credits) is not int or reserve_credits < 0:
        raise ValueError("Invalid reserve_credits")

    if type(allow_unknown) is not bool:
        raise ValueError("Invalid allow_unknown")

    remaining = snapshot.credits_left

    if remaining is None:
        if allow_unknown:
            return CreditDecision(
                allowed=True,
                remaining=None,
                reason="Provider credits unknown; explicitly allowed",
            )

        raise ProviderCreditStatusUnknown(
            "Provider remaining credits unavailable"
        )

    if remaining < required_credits + reserve_credits:
        raise ProviderCreditLimitReached(
            "Insufficient provider credits for requested operation"
        )

    return CreditDecision(
        allowed=True,
        remaining=remaining,
        reason="Sufficient provider credits reported",
    )
