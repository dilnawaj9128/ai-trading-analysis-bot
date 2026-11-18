"""Persistent single-use approval for offline credit-refresh preparation.

Does not authorize HTTP requests or reserve API credits.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


class CreditRefreshApprovalRequired(RuntimeError):
    pass


class CreditRefreshApprovalAlreadyUsed(RuntimeError):
    pass


def claim_credit_refresh_approval(
    *,
    approval_id,
    explicitly_approved=False,
    path="data/api_usage/credit_refresh_claim.json",
    now=None,
):
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ValueError("Non-empty approval_id required")

    if type(explicitly_approved) is not bool:
        raise ValueError("Explicit approval flag must be boolean")

    if not explicitly_approved:
        raise CreditRefreshApprovalRequired(
            "Explicit credit-refresh approval required"
        )

    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "claim_id": uuid.uuid4().hex,
        "approval_id": approval_id,
        "claimed_at": now.astimezone(timezone.utc).isoformat(),
        "status": "CLAIMED_OFFLINE",
    }

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise CreditRefreshApprovalAlreadyUsed(
            "Credit-refresh approval already claimed"
        ) from exc

    # Retain the claim on write failure: fail closed.
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())

    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

    return payload
