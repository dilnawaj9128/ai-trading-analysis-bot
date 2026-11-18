"""Locked reservation lifecycle transitions for research API requests.

Does not perform HTTP requests or trading execution.
"""

import fcntl
import os
from pathlib import Path

from market_data.provider_credit_state import DEFAULT_PATH
from market_data.unified_request_guard import (
    _load_ledger,
    _save_json_atomic,
)


def transition_authorization(
    *,
    provider_state_path=DEFAULT_PATH,
    request_id,
    status,
):
    """Transition one request while preserving aggregate accounting."""

    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("Valid request_id required")

    if status not in ("SETTLED", "UNCERTAIN"):
        raise ValueError("Unsupported reservation transition")

    # No verified request-specific reconciliation exists yet.
    # Never release reserved credits without trusted evidence.
    if status == "SETTLED":
        raise ValueError(
            "Settlement requires verified reconciliation"
        )

    provider_path = Path(provider_state_path)

    lock_path = provider_path.with_name(
        provider_path.name + ".lock"
    )

    ledger_path = provider_path.with_name(
        provider_path.name + ".reservations.json"
    )

    # Never create an empty ledger during a transition.
    if not ledger_path.exists():
        raise ValueError("Reservation ledger missing")

    provider_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        try:
            # Verify that the locked file descriptor still
            # represents the lock file reachable by its path.
            try:
                locked_stat = os.fstat(lock_file.fileno())
                path_stat = os.stat(lock_path)
            except OSError as exc:
                raise RuntimeError(
                    "Authorization lock identity unavailable"
                ) from exc

            if (
                locked_stat.st_dev != path_stat.st_dev
                or locked_stat.st_ino != path_stat.st_ino
            ):
                raise RuntimeError(
                    "Authorization lock identity changed"
                )

            ledger = _load_ledger(ledger_path)

            # A missing ledger must not be treated as an empty ledger.
            if not ledger_path.exists():
                raise ValueError("Reservation ledger missing")

            entry = ledger["requests"].get(request_id)

            if entry is None:
                raise ValueError("Unknown request ID")

            current_status = entry["status"]

            if current_status != "PENDING":
                raise ValueError(
                    "Only PENDING reservations can transition"
                )

            if status == "SETTLED":
                credits = entry["credits"]

                if ledger["reserved"] < credits:
                    raise ValueError(
                        "Reservation accounting mismatch"
                    )

                ledger["reserved"] -= credits

            # UNCERTAIN reservations remain counted.
            entry["status"] = status

            _save_json_atomic(ledger_path, ledger)

            return {
                "request_id": request_id,
                "status": status,
                "reserved": ledger["reserved"],
            }

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
