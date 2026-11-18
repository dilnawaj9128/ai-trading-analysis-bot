"""Offline persistent credit-refresh lifecycle store.

No HTTP requests, API keys, quota changes, or trading execution.
"""

import fcntl
import json
import os
import tempfile
import uuid

from datetime import datetime, timezone
from pathlib import Path

from market_data.credit_refresh_lifecycle import (
    evaluate_refresh_lifecycle,
)


class CreditRefreshStoreError(RuntimeError):
    pass


def _utc(now):
    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")

    return now.astimezone(timezone.utc)


def _load(path):
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if (
            type(data) is not dict
            or set(data) != {
                "version",
                "attempt_id",
                "attempted_at",
                "status",
            }
            or type(data["version"]) is not int
            or data["version"] != 1
            or type(data["attempt_id"]) is not str
            or len(data["attempt_id"]) != 32
            or any(
                c not in "0123456789abcdef"
                for c in data["attempt_id"]
            )
            or data["status"] not in (
                "CLAIMED",
                "UNCERTAIN",
                "COMPLETED",
            )
        ):
            raise ValueError("Invalid lifecycle state")

        attempted_at = datetime.fromisoformat(
            data["attempted_at"]
        )

        if attempted_at.tzinfo is None:
            raise ValueError("Naive lifecycle timestamp")

        return data

    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise CreditRefreshStoreError(
            "Invalid persistent lifecycle state"
        ) from exc


def _save(path, data):
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".credit_refresh_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _claim_refresh_attempt_internal(
    *,
    path,
    now=None,
    cooldown_seconds=3600,
):
    """Persist an offline claim; never executes a request."""

    now = _utc(now)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = path.with_name(path.name + ".lock")

    with open(lock_path, "a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        try:
            locked = os.fstat(lock_file.fileno())
            current = os.stat(lock_path)

            if (
                locked.st_dev != current.st_dev
                or locked.st_ino != current.st_ino
            ):
                raise CreditRefreshStoreError(
                    "Lifecycle lock identity changed"
                )

            previous = _load(path)

            last_attempt_at = None
            last_status = None

            if previous is not None:
                last_attempt_at = datetime.fromisoformat(
                    previous["attempted_at"]
                )
                last_status = previous["status"]

            decision = evaluate_refresh_lifecycle(
                last_attempt_at=last_attempt_at,
                last_status=last_status,
                now=now,
                cooldown_seconds=cooldown_seconds,
            )

            if not decision.allowed:
                raise CreditRefreshStoreError(
                    f"Refresh blocked: {decision.reason}"
                )

            data = {
                "version": 1,
                "attempt_id": uuid.uuid4().hex,
                "attempted_at": now.isoformat(),
                "status": "CLAIMED",
            }

            _save(path, data)

            return data

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def transition_refresh_attempt(
    *,
    path,
    attempt_id,
    status,
):
    """Persist a conservative lifecycle transition."""

    if status == "COMPLETED":
        raise ValueError(
            "Completion requires verified provider reconciliation"
        )

    if status != "UNCERTAIN":
        raise ValueError("Unsupported lifecycle transition")

    path = Path(path)
    lock_path = path.with_name(path.name + ".lock")

    if not path.exists():
        raise CreditRefreshStoreError(
            "Lifecycle state missing"
        )

    with open(lock_path, "a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        try:
            locked = os.fstat(lock_file.fileno())
            current = os.stat(lock_path)

            if (
                locked.st_dev != current.st_dev
                or locked.st_ino != current.st_ino
            ):
                raise CreditRefreshStoreError(
                    "Lifecycle lock identity changed"
                )

            data = _load(path)

            if data is None:
                raise CreditRefreshStoreError(
                    "Lifecycle state missing"
                )

            if data["attempt_id"] != attempt_id:
                raise CreditRefreshStoreError(
                    "Attempt ID mismatch"
                )

            if data["status"] != "CLAIMED":
                raise CreditRefreshStoreError(
                    "Only CLAIMED attempts may transition"
                )

            data["status"] = status
            _save(path, data)

            return data

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)



def claim_refresh_attempt(
    *,
    path,
    now=None,
    cooldown_seconds=3600,
):
    """Deny direct lifecycle claims without approval coordination."""
    raise CreditRefreshStoreError(
        "Direct lifecycle claims disabled; approval binding required"
    )
