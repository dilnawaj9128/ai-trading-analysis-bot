"""Durable offline execution tracking.

No HTTP, no settlement and no automated trading.
Interrupted operations fail closed.
"""

import fcntl
import json
import os
import tempfile
from pathlib import Path

from market_data.manual_refresh_preparation import (
    verify_prepared_manual_refresh,
)
from market_data.twelve_data_client import reserve_request


class ExecutionStateError(RuntimeError):
    pass


def _read(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ExecutionStateError(
            "Execution evidence missing or invalid"
        ) from exc

    if (
        type(data) is not dict
        or set(data) != {
            "version", "approval_claim_id",
            "attempt_id", "status"
        }
        or data["version"] != 1
        or data["status"] not in {
            "PREPARED",
            "RESERVATION_STARTED",
            "BUDGET_RESERVED",
            "REQUEST_ATTEMPTED",
            "UNCERTAIN",
        }
    ):
        raise ExecutionStateError("Invalid execution state")

    for key in ("approval_claim_id", "attempt_id"):
        value = data[key]
        if (
            type(value) is not str
            or len(value) != 32
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ExecutionStateError("Invalid execution identity")

    return data


def _save(path, data):
    path = Path(path)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=".execution_",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_execution(
    *,
    approval_path,
    lifecycle_path,
    approval_id,
    execution_path,
):
    execution_path = Path(execution_path)
    approval_path = Path(approval_path)
    lifecycle_path = Path(lifecycle_path)
    marker = approval_path.with_name(
        approval_path.name + ".consumed"
    )

    paths = (
        approval_path,
        lifecycle_path,
        marker,
        execution_path,
        execution_path.with_name(
            execution_path.name + ".lock"
        ),
    )

    if len({p.resolve() for p in paths}) != len(paths):
        raise ExecutionStateError("Overlapping execution paths")

    evidence = verify_prepared_manual_refresh(
        approval_path=approval_path,
        lifecycle_path=lifecycle_path,
        approval_id=approval_id,
    )

    execution_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": 1,
        "approval_claim_id": evidence["approval_claim_id"],
        "attempt_id": evidence["attempt_id"],
        "status": "PREPARED",
    }

    try:
        fd = os.open(
            execution_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise ExecutionStateError(
            "Execution already exists; no retry"
        ) from exc

    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle)
        handle.flush()
        os.fsync(handle.fileno())

    directory = os.open(execution_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

    return data


def _transition(path, expected, new_status):
    path = Path(path)
    lock = path.with_name(path.name + ".lock")

    if not path.exists():
        raise ExecutionStateError("Execution state missing")

    with open(lock, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

        try:
            locked = os.fstat(handle.fileno())
            current = os.stat(lock)

            if (
                locked.st_dev != current.st_dev
                or locked.st_ino != current.st_ino
            ):
                raise ExecutionStateError(
                    "Execution lock identity changed"
                )

            data = _read(path)

            if data["status"] != expected:
                raise ExecutionStateError(
                    "Invalid or duplicate execution transition"
                )

            data["status"] = new_status
            _save(path, data)
            return data

        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def reserve_execution_budget(
    *,
    execution_path,
    budget_path,
    now,
):
    """Reserve once; a crash leaves a non-retryable marker."""

    _transition(
        execution_path,
        "PREPARED",
        "RESERVATION_STARTED",
    )

    # Existing conservative quota function handles budget locks.
    reserve_request(path=budget_path, now=now)

    return _transition(
        execution_path,
        "RESERVATION_STARTED",
        "BUDGET_RESERVED",
    )


def record_request_attempt(*, execution_path):
    """Persist intent only. Does not execute HTTP."""

    return _transition(
        execution_path,
        "BUDGET_RESERVED",
        "REQUEST_ATTEMPTED",
    )


def mark_uncertain(*, execution_path):
    return _transition(
        execution_path,
        "REQUEST_ATTEMPTED",
        "UNCERTAIN",
    )
