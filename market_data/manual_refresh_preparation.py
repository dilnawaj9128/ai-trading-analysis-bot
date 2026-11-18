"""Durable offline preparation for one credit-refresh attempt.

No HTTP, quota reservations, settlement or trading execution.
"""

from market_data.credit_refresh_approval import (
    claim_credit_refresh_approval,
)
from market_data.credit_refresh_coordinator import (
    prepare_offline_refresh,
)


def prepare_manual_refresh(
    *,
    approval_id,
    approval_path,
    lifecycle_path,
    explicitly_approved=False,
    now=None,
):
    if explicitly_approved is not True:
        raise ValueError("Explicit approval required")

    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ValueError("Valid approval ID required")

    claim = claim_credit_refresh_approval(
        approval_id=approval_id,
        explicitly_approved=True,
        path=approval_path,
        now=now,
    )

    attempt = prepare_offline_refresh(
        approval_path=approval_path,
        lifecycle_path=lifecycle_path,
        approval_id=approval_id,
        now=now,
    )

    return {
        "approval_claim_id": claim["claim_id"],
        "attempt_id": attempt["attempt_id"],
        "status": attempt["status"],
        "offline_only": True,
        "http_authorized": False,
        "settlement_authorized": False,
    }


def verify_prepared_manual_refresh(
    *,
    approval_path,
    lifecycle_path,
    approval_id,
):
    """Verify persisted approval/lifecycle binding without side effects."""
    import json
    from pathlib import Path
    from datetime import datetime

    from market_data.credit_refresh_store import _load

    approval_path = Path(approval_path)
    lifecycle_path = Path(lifecycle_path)
    marker_path = approval_path.with_name(
        approval_path.name + ".consumed"
    )

    protected = [
        approval_path.resolve(),
        marker_path.resolve(),
        lifecycle_path.resolve(),
    ]

    if len(set(protected)) != 3:
        raise ValueError("Overlapping approval/lifecycle paths")

    try:
        approval = json.loads(approval_path.read_text())
        marker = json.loads(marker_path.read_text())
        lifecycle = _load(lifecycle_path)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("Refresh evidence unavailable or invalid") from exc

    if not all(isinstance(x, dict) for x in (approval, marker, lifecycle)):
        raise ValueError("Invalid refresh evidence")

    claim_id = approval.get("claim_id")
    attempt_id = lifecycle.get("attempt_id")

    def valid_id(value):
        return (
            type(value) is str
            and len(value) == 32
            and all(c in "0123456789abcdef" for c in value)
        )

    if not valid_id(claim_id) or not valid_id(attempt_id):
        raise ValueError("Invalid claim or attempt ID")

    if (
        approval.get("version") != 1
        or approval.get("status") != "CLAIMED_OFFLINE"
        or approval.get("approval_id") != approval_id
        or marker.get("version") != 1
        or marker.get("status") != "CONSUMED_OFFLINE"
        or marker.get("approval_id") != approval_id
        or marker.get("approval_claim_id") != claim_id
        or lifecycle.get("status") != "CLAIMED"
    ):
        raise ValueError("Approval/lifecycle binding mismatch")

    try:
        claimed_at = datetime.fromisoformat(approval["claimed_at"])
        attempted_at = datetime.fromisoformat(lifecycle["attempted_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid evidence timestamp") from exc

    if (
        claimed_at.tzinfo is None
        or attempted_at.tzinfo is None
        or attempted_at < claimed_at
    ):
        raise ValueError("Invalid refresh attempt chronology")

    return {
        "verified_local_binding": True,
        "approval_claim_id": claim_id,
        "attempt_id": attempt_id,
        "http_authorized": False,
        "settlement_authorized": False,
    }
