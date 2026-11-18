"""Offline approval/lifecycle binding coordinator.

No HTTP, API key access, quota reservations, or trading.
This is not a production request authorization mechanism.
"""

import json
import os
from pathlib import Path

from market_data.credit_refresh_store import (
    _claim_refresh_attempt_internal,
)


class CreditRefreshBindingError(RuntimeError):
    pass


def prepare_offline_refresh(
    *,
    approval_path,
    lifecycle_path,
    approval_id,
    now=None,
):
    """Require an existing approval claim before lifecycle preparation."""

    approval_path = Path(approval_path)
    lifecycle_path = Path(lifecycle_path)

    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ValueError("Valid approval_id required")

    # Prevent relative-path and symlink aliases from overlapping persistent
    # approval, consumption marker, lifecycle, and lifecycle lock files.
    # This is a defensive check, not a substitute for filesystem permissions.
    marker_path = approval_path.with_name(approval_path.name + ".consumed")
    lifecycle_lock_path = lifecycle_path.with_name(lifecycle_path.name + ".lock")
    protected_paths = (
        approval_path, marker_path, lifecycle_path, lifecycle_lock_path,
    )
    if len({p.resolve(strict=False) for p in protected_paths}) != 4:
        raise CreditRefreshBindingError(
            "Approval, marker, lifecycle and lock paths must differ"
        )

    try:
        approval = json.loads(
            approval_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise CreditRefreshBindingError(
            "Approval claim unavailable or invalid"
        ) from exc

    if (
        type(approval) is not dict
        or type(approval.get("version")) is not int
        or approval.get("version") != 1
        or approval.get("status") != "CLAIMED_OFFLINE"
        or approval.get("approval_id") != approval_id
        or type(approval.get("claim_id")) is not str
        or len(approval["claim_id"]) != 32
        or any(c not in "0123456789abcdef" for c in approval["claim_id"])
    ):
        raise CreditRefreshBindingError(
            "Approval claim verification failed"
        )

    # A durable approval claim must already exist.
    # Lifecycle claim is separately durable and fail-closed.
    # This does not establish a multi-file atomic transaction.
    # Persist a single-use consumption marker BEFORE lifecycle creation.
    # A crash leaves this marker in place and blocks automatic reuse.
    marker_payload = {
        "version": 1,
        "approval_id": approval_id,
        "approval_claim_id": approval["claim_id"],
        "status": "CONSUMED_OFFLINE",
    }

    try:
        fd = os.open(
            marker_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise CreditRefreshBindingError(
            "Approval already consumed; manual recovery required"
        ) from exc

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(marker_payload, handle)
        handle.flush()
        os.fsync(handle.fileno())

    directory_fd = os.open(marker_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

    lifecycle = _claim_refresh_attempt_internal(
        path=lifecycle_path,
        now=now,
    )

    return {
        "approval_id": approval_id,
        "approval_claim_id": approval["claim_id"],
        "attempt_id": lifecycle["attempt_id"],
        "status": lifecycle["status"],
        "offline_only": True,
    }
