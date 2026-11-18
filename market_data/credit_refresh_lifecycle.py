"""Offline credit-refresh lifecycle validation.

No HTTP, API key access, or filesystem changes.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class RefreshLifecycleDecision:
    allowed: bool
    action: str
    reason: str


def evaluate_refresh_lifecycle(
    *,
    last_attempt_at=None,
    last_status=None,
    now=None,
    cooldown_seconds=3600,
):
    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware now required")

    if type(cooldown_seconds) is not int or cooldown_seconds < 0:
        raise ValueError("Invalid cooldown")

    if last_status not in (
        None,
        "CLAIMED",
        "UNCERTAIN",
        "COMPLETED",
    ):
        raise ValueError("Invalid lifecycle status")

    if (last_attempt_at is None) != (last_status is None):
        raise ValueError("Incomplete lifecycle history")

    if last_attempt_at is not None:
        if (
            not isinstance(last_attempt_at, datetime)
            or last_attempt_at.tzinfo is None
        ):
            raise ValueError("Timezone-aware attempt timestamp required")

        if last_attempt_at > now:
            return RefreshLifecycleDecision(
                False, "BLOCK", "Future attempt timestamp"
            )

    if last_status in ("CLAIMED", "UNCERTAIN"):
        return RefreshLifecycleDecision(
            False, "BLOCK", "Unresolved previous refresh attempt"
        )

    if last_attempt_at is not None:
        elapsed = now - last_attempt_at

        if elapsed < timedelta(seconds=cooldown_seconds):
            return RefreshLifecycleDecision(
                False, "COOLDOWN", "Refresh cooldown active"
            )

    return RefreshLifecycleDecision(
        True,
        "ELIGIBLE",
        "Offline lifecycle conditions satisfied",
    )
