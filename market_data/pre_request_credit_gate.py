"""Pre-request provider credit gate. No network calls."""

from dataclasses import dataclass
from datetime import datetime, timezone

from market_data.provider_credit_guard import (
    check_provider_credits,
    ProviderCreditStatusUnknown,
)
from market_data.provider_credit_state import (
    DEFAULT_PATH,
    load_credit_state,
)


@dataclass(frozen=True)
class PreRequestDecision:
    allowed: bool
    remaining_credits: int
    required_credits: int
    reserve_credits: int


def check_before_request(
    *,
    path=DEFAULT_PATH,
    now=None,
    required_credits=1,
    reserve_credits=20,
    max_age_seconds=300,
) -> PreRequestDecision:
    """Reject requests when provider credit status is unknown or insufficient."""

    if now is None:
        now = datetime.now(timezone.utc)

    snapshot = load_credit_state(
        path=path,
        now=now,
        max_age_seconds=max_age_seconds,
    )

    if snapshot is None:
        raise ProviderCreditStatusUnknown(
            "Provider credit snapshot missing or expired"
        )

    result = check_provider_credits(
        snapshot,
        required_credits=required_credits,
        reserve_credits=reserve_credits,
        allow_unknown=False,
    )

    return PreRequestDecision(
        allowed=result.allowed,
        remaining_credits=result.remaining,
        required_credits=required_credits,
        reserve_credits=reserve_credits,
    )
