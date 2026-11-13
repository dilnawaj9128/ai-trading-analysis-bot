"""Conservative provider-credit snapshot refresh.

Coordinates snapshot writes with authorization using the same file lock.
Does not execute HTTP requests or trading operations.
"""

import fcntl
import json

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from market_data.api_credit_monitor import parse_credit_headers
from market_data.provider_credit_state import (
    DEFAULT_PATH,
    save_credit_state,
)


@dataclass(frozen=True)
class CreditRefreshResult:
    updated: bool
    credits_left: int | None
    reason: str


def refresh_credits_from_response(
    response,
    *,
    path=DEFAULT_PATH,
    now=None,
) -> CreditRefreshResult:

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")

    now = now.astimezone(timezone.utc)

    headers = getattr(response, "headers", None)

    if headers is None:
        return CreditRefreshResult(
            updated=False,
            credits_left=None,
            reason="Response headers unavailable",
        )

    try:
        snapshot = parse_credit_headers(headers)
    except (TypeError, AttributeError):
        return CreditRefreshResult(
            updated=False,
            credits_left=None,
            reason="Invalid response headers",
        )

    if snapshot.credits_left is None:
        return CreditRefreshResult(
            updated=False,
            credits_left=None,
            reason="Provider remaining credits unavailable",
        )

    provider_path = Path(path)
    provider_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = provider_path.with_name(
        provider_path.name + ".lock"
    )

    with open(lock_path, "a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        try:
            if provider_path.exists():
                try:
                    current = json.loads(provider_path.read_text())
                    if (
                        type(current) is not dict
                        or current.get("version") != 1
                    ):
                        raise ValueError("Invalid provider state")

                    observed_at = datetime.fromisoformat(
                        current["observed_at"]
                    ).astimezone(timezone.utc)

                    existing_left = current["credits_left"]

                    if (
                        type(existing_left) is not int
                        or existing_left < 0
                    ):
                        raise ValueError("Invalid credits_left")

                except (OSError, ValueError, TypeError, KeyError) as exc:
                    raise ValueError(
                        "Invalid existing provider credit state"
                    ) from exc

                if now < observed_at:
                    return CreditRefreshResult(
                        updated=False,
                        credits_left=existing_left,
                        reason="Older observation rejected",
                    )

                if (
                    now == observed_at
                    and snapshot.credits_left > existing_left
                ):
                    return CreditRefreshResult(
                        updated=False,
                        credits_left=existing_left,
                        reason="Equal-time credit increase rejected",
                    )

            save_credit_state(
                snapshot,
                path=provider_path,
                now=now,
            )

            return CreditRefreshResult(
                updated=True,
                credits_left=snapshot.credits_left,
                reason="Provider credit snapshot updated",
            )

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
