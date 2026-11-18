from market_data.basic8_credit_policy import PROVIDER_RESERVE_CREDITS
"""Provider credit bootstrap policy.

Decision-only module. No HTTP calls or local budget reservations.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from market_data.provider_credit_guard import (
    ProviderCreditLimitReached,
    ProviderCreditStatusUnknown,
)
from market_data.provider_credit_state import (
    DEFAULT_PATH,
    load_credit_state,
)
from market_data.pre_request_credit_gate import check_before_request


@dataclass(frozen=True)
class BootstrapDecision:
    action: str
    reason: str
    requires_explicit_approval: bool


def decide_credit_bootstrap(
    *,
    path=DEFAULT_PATH,
    now=None,
    max_age_seconds=300,
    bootstrap_approved=False,
):
    if type(bootstrap_approved) is not bool:
        raise ValueError("Invalid bootstrap_approved")

    if now is None:
        now = datetime.now(timezone.utc)

    snapshot = load_credit_state(
        path=path,
        now=now,
        max_age_seconds=max_age_seconds,
    )

    if snapshot is None or snapshot.credits_left is None:
        if bootstrap_approved:
            return BootstrapDecision(
                action="BOOTSTRAP",
                reason="One explicitly approved bootstrap request may be attempted",
                requires_explicit_approval=False,
            )

        return BootstrapDecision(
            action="REQUIRE_APPROVAL",
            reason="Provider credits unknown or expired",
            requires_explicit_approval=True,
        )

    try:
        check_before_request(
            path=path,
            now=now,
            max_age_seconds=max_age_seconds,
            reserve_credits=PROVIDER_RESERVE_CREDITS,
        )
    except ProviderCreditLimitReached:
        return BootstrapDecision(
            action="BLOCK",
            reason="Insufficient reported provider credits",
            requires_explicit_approval=False,
        )
    except ProviderCreditStatusUnknown:
        return BootstrapDecision(
            action="REQUIRE_APPROVAL",
            reason="Provider credit status unavailable",
            requires_explicit_approval=True,
        )

    return BootstrapDecision(
        action="NORMAL",
        reason="Fresh provider credit snapshot permits normal requests",
        requires_explicit_approval=False,
    )
