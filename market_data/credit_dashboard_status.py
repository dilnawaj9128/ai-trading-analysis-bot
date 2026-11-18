from market_data.basic8_credit_policy import PROVIDER_RESERVE_CREDITS
"""Read-only provider credit status for research dashboards."""

from datetime import datetime, timezone

from market_data.provider_credit_state import (
    DEFAULT_PATH,
    load_credit_state,
)


def get_credit_dashboard_status(
    *,
    path=DEFAULT_PATH,
    now=None,
    required_credits=1,
    reserve_credits=PROVIDER_RESERVE_CREDITS,
):
    now = now or datetime.now(timezone.utc)

    snapshot = load_credit_state(
        path=path,
        now=now,
    )

    if snapshot is None or snapshot.credits_left is None:
        return {
            "status": "UNKNOWN",
            "credits_left": None,
            "credits_used": None,
            "request_allowed": False,
            "message": "Provider credits missing or expired",
        }

    allowed = (
        snapshot.credits_left
        >= required_credits + reserve_credits
    )

    return {
        "status": "READY" if allowed else "LOW_CREDITS",
        "credits_left": snapshot.credits_left,
        "credits_used": snapshot.credits_used,
        "request_allowed": allowed,
        "message": (
            "Provider credit threshold satisfied"
            if allowed
            else "Insufficient provider credits for guarded request"
        ),
    }
