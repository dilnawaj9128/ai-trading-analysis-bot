"""Persistent request-level credit reservation registry.

Research-only. No HTTP requests or trading execution.
"""

import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from market_data.reservation_lifecycle import (
    CreditReservation,
    ReservationStatus,
    settle_reservation,
    mark_uncertain,
    outstanding_credits,
)


class ReservationRegistryError(RuntimeError):
    pass


@contextmanager
def _locked(path):
    lock_path = path.with_name(path.name + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read(path):
    if not path.exists():
        return {"version": 1, "requests": {}}

    try:
        payload = json.loads(path.read_text())

        if (
            type(payload) is not dict
            or payload.get("version") != 1
            or type(payload.get("requests")) is not dict
        ):
            raise ValueError("Invalid registry structure")

        for request_id, entry in payload["requests"].items():
            if (
                type(entry) is not dict
                or entry.get("request_id") != request_id
            ):
                raise ValueError("Invalid reservation entry")

            CreditReservation(
                request_id=entry["request_id"],
                credits=entry["credits"],
                status=ReservationStatus(entry["status"]),
            )

        return payload

    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ReservationRegistryError(
            "Invalid reservation registry"
        ) from exc


def _write(path, payload):
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=".registry_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _entry(item):
    return {
        "request_id": item.request_id,
        "credits": item.credits,
        "status": item.status.value,
    }


def _reservation(entry):
    return CreditReservation(
        request_id=entry["request_id"],
        credits=entry["credits"],
        status=ReservationStatus(entry["status"]),
    )


def create_reservation(*, path, credits=1):
    path = Path(path)

    with _locked(path):
        payload = _read(path)
        request_id = uuid.uuid4().hex

        if request_id in payload["requests"]:
            raise ReservationRegistryError("Duplicate request ID")

        item = CreditReservation(request_id, credits)
        payload["requests"][request_id] = _entry(item)
        _write(path, payload)

        return item


def transition_reservation(*, path, request_id, status):
    path = Path(path)

    with _locked(path):
        payload = _read(path)

        if request_id not in payload["requests"]:
            raise ReservationRegistryError("Unknown request ID")

        item = _reservation(payload["requests"][request_id])

        if status == ReservationStatus.SETTLED:
            updated = settle_reservation(item)
        elif status == ReservationStatus.UNCERTAIN:
            updated = mark_uncertain(item)
        else:
            raise ValueError("Unsupported transition")

        payload["requests"][request_id] = _entry(updated)
        _write(path, payload)

        return updated


def get_outstanding_credits(*, path):
    path = Path(path)

    with _locked(path):
        payload = _read(path)

        reservations = [
            _reservation(entry)
            for entry in payload["requests"].values()
        ]

        return outstanding_credits(reservations)
