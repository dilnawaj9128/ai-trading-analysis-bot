"""Persistent, one-time bootstrap approval claim.

No HTTP requests, trading execution, or API budget reservations.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class BootstrapApprovalRequired(RuntimeError):
    pass


class BootstrapApprovalAlreadyUsed(RuntimeError):
    pass


def claim_bootstrap_approval(
    *,
    approval_id,
    explicitly_approved=False,
    path="data/api_usage/bootstrap_claim.json",
    now=None,
):
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ValueError("Non-empty approval_id required")

    if type(explicitly_approved) is not bool:
        raise ValueError("explicitly_approved must be boolean")

    if not explicitly_approved:
        raise BootstrapApprovalRequired(
            "Explicit bootstrap approval required"
        )

    now = now if now is not None else datetime.now(timezone.utc)

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "approval_id": approval_id,
        "claimed_at": now.astimezone(timezone.utc).isoformat(),
        "status": "claimed",
    }

    # O_EXCL makes file creation atomic across processes.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise BootstrapApprovalAlreadyUsed(
            "Bootstrap approval already claimed"
        ) from exc

    # Fail closed: if writing fails, retain the claim file.
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())

    return payload
