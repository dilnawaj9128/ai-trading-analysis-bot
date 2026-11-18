"""Offline-only provider credit refresh policy.

No HTTP, API key access, filesystem writes, or budget reservations.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CreditRefreshDecision:
    action: str
    reason: str
    requires_approval: bool


def decide_credit_refresh(
    *,
    snapshot_status: str,
    explicitly_approved: bool = False,
    local_budget_available: bool = False,
    cooldown_satisfied: bool = False,
    recovery_required: bool = False,
) -> CreditRefreshDecision:

    if snapshot_status not in (
        "READY",
        "LOW_CREDITS",
        "UNKNOWN",
    ):
        raise ValueError("Invalid snapshot status")

    for value in (
        explicitly_approved,
        local_budget_available,
        cooldown_satisfied,
        recovery_required,
    ):
        if type(value) is not bool:
            raise ValueError("Policy flags must be boolean")

    if recovery_required:
        return CreditRefreshDecision(
            "BLOCK",
            "Authorization recovery is required",
            False,
        )

    if snapshot_status == "READY":
        return CreditRefreshDecision(
            "NO_REFRESH",
            "Fresh provider credits are sufficient",
            False,
        )

    if snapshot_status == "LOW_CREDITS":
        return CreditRefreshDecision(
            "BLOCK",
            "Fresh provider credits are insufficient",
            False,
        )

    if not local_budget_available:
        return CreditRefreshDecision(
            "BLOCK",
            "Local API budget unavailable",
            False,
        )

    if not cooldown_satisfied:
        return CreditRefreshDecision(
            "BLOCK",
            "Credit refresh cooldown active",
            False,
        )

    if not explicitly_approved:
        return CreditRefreshDecision(
            "REQUIRE_APPROVAL",
            "Explicit approval required for credit refresh",
            True,
        )

    return CreditRefreshDecision(
        "ELIGIBLE",
        "Offline policy conditions satisfied; no request executed",
        False,
    )
