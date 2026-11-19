"""Stage 52D Part 4B: offline, single-use recovery approval.

No HTTP, no budget reservation, no probe state mutation.
An offline claim is NOT permission to execute network requests.
"""

import fcntl
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_data.recovery_preflight import evaluate_preflight


class RecoveryApprovalBlocked(RuntimeError):
    pass


def _utc(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise RecoveryApprovalBlocked("Aware UTC time required")
    return now.astimezone(timezone.utc)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    try:
        result = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise RecoveryApprovalBlocked("Approval evidence invalid") from exc

    if type(result) is not dict:
        raise RecoveryApprovalBlocked("Invalid approval schema")
    return result


def _exclusive_create(path, payload):
    """Never overwrite approval/claim evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )

    with os.fdopen(fd, "w") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())

    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextmanager
def _lock(path):
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            a = os.fstat(handle.fileno())
            b = os.stat(lock_path)
            if a.st_ino != b.st_ino or a.st_dev != b.st_dev:
                raise RecoveryApprovalBlocked("Approval lock replaced")
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _check_preflight(root, case_path, now):
    result = evaluate_preflight(
        root=root,
        case_path=case_path,
        now=now,
    )

    if result["preflight"] != "READY_FOR_APPROVAL_REVIEW":
        raise RecoveryApprovalBlocked(
            "Recovery preflight blocked: " +
            ",".join(result["reasons"])
        )

    return result


def prepare_offline_approval(
    *,
    root,
    case_path,
    approval_path,
    explicitly_approved=False,
    now=None,
):
    """Prepare a one-time offline approval, with explicit consent."""
    if explicitly_approved is not True:
        raise RecoveryApprovalBlocked("Explicit new-request approval required")

    now = _utc(now)
    approval_path = Path(approval_path)
    case_path = Path(case_path)

    with _lock(approval_path):
        if approval_path.exists():
            raise RecoveryApprovalBlocked("Approval already prepared")

        _check_preflight(root, case_path, now)

        payload = {
            "version": 1,
            "approval_id": uuid.uuid4().hex,
            "status": "PREPARED_OFFLINE",
            "purpose": "NEW_RESEARCH_REQUEST_NOT_OLD_RETRY",
            "created_at_utc": now.isoformat(),
            "expires_at_utc": (
                now + timedelta(minutes=2)
            ).isoformat(),
            "case_sha256": _digest(case_path),
            "http_authorized": False,
            "retry_authorized": False,
            "trading_enabled": False,
        }

        _exclusive_create(approval_path, payload)
        return payload


def claim_offline_approval(
    *,
    root,
    case_path,
    approval_path,
    now=None,
):
    """Claim once. No network execution or automatic budget reservation."""
    now = _utc(now)
    approval_path = Path(approval_path)
    marker_path = Path(str(approval_path) + ".consumed")
    case_path = Path(case_path)

    with _lock(approval_path):
        if marker_path.exists():
            raise RecoveryApprovalBlocked("Approval already consumed")

        approval = _load(approval_path)

        if (
            approval.get("version") != 1
            or approval.get("status") != "PREPARED_OFFLINE"
            or approval.get("purpose")
                != "NEW_RESEARCH_REQUEST_NOT_OLD_RETRY"
            or approval.get("http_authorized") is not False
        ):
            raise RecoveryApprovalBlocked("Approval state invalid")

        if _digest(case_path) != approval.get("case_sha256"):
            raise RecoveryApprovalBlocked("Recovery case changed")

        try:
            created = datetime.fromisoformat(
                approval["created_at_utc"]
            )
            expires = datetime.fromisoformat(
                approval["expires_at_utc"]
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise RecoveryApprovalBlocked("Invalid approval time") from exc

        if (
            created.tzinfo is None
            or expires.tzinfo is None
            or now < created
            or now >= expires
            or expires - created != timedelta(minutes=2)
        ):
            raise RecoveryApprovalBlocked("Approval expired or invalid")

        approval_id = approval.get("approval_id")
        if (
            type(approval_id) is not str
            or len(approval_id) != 32
            or any(c not in "0123456789abcdef" for c in approval_id)
        ):
            raise RecoveryApprovalBlocked("Invalid approval ID")

        # Recheck evidence, provider credits and budget at claim time.
        _check_preflight(root, case_path, now)

        marker = {
            "version": 1,
            "approval_id": approval_id,
            "status": "CONSUMED_OFFLINE",
            "claimed_at_utc": now.isoformat(),
            "http_authorized": False,
            "retry_authorized": False,
            "trading_enabled": False,
        }

        try:
            _exclusive_create(marker_path, marker)
        except FileExistsError as exc:
            raise RecoveryApprovalBlocked(
                "Duplicate approval claim"
            ) from exc

        return marker
