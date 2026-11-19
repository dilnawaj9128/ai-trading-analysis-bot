"""Stage 28C: shared-lock, read-only probe-state safety gate.

This is *not* an authorization to consume provider credits. Existing budget,
provider-credit, and explicit approval requirements still apply independently.
"""
import fcntl
import functools
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PROBE_STATE = Path("data/api_usage/approved_research_probe.json")


class CrossPathProbeBlocked(RuntimeError):
    """Unresolved or untrustworthy probe history; do not make HTTP requests."""


def check_probe_state(path=None):
    """Check history under a caller-held probe lock, without modifying it."""
    path = Path(PROBE_STATE if path is None else path)
    if not path.exists():
        return "NO_PROBE_HISTORY"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if type(data) is not dict or data.get("version") != 1:
            raise ValueError("Invalid probe schema")
        attempts = data.get("attempts")
        if type(attempts) is not list:
            raise ValueError("Invalid attempts")
        for attempt in attempts:
            if type(attempt) is not dict:
                raise ValueError("Invalid attempt entry")
            if attempt.get("status") not in {
                "INTENT", "BUDGET_RESERVED", "REQUEST_ATTEMPTED",
                "UNCERTAIN", "VERIFIED",
            }:
                raise ValueError("Invalid attempt status")
            started = datetime.fromisoformat(attempt["started_at"])
            if started.tzinfo is None or started.astimezone(timezone.utc) > datetime.now(timezone.utc):
                raise ValueError("Invalid attempt timestamp")
        if attempts and attempts[-1]["status"] != "VERIFIED":
            raise CrossPathProbeBlocked(
                "Last research probe attempt unresolved; legacy fetch blocked"
            )
        return "VERIFIED" if attempts else "NO_PROBE_ATTEMPTS"
    except CrossPathProbeBlocked:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise CrossPathProbeBlocked("Probe history unreadable or invalid; fetch blocked") from exc


@contextmanager
def hold_probe_gate(path=None):
    """Hold shared advisory lock throughout another client's request.

    The approved probe takes an exclusive lock on the same stable lock file,
    preventing a concurrent probe from changing the last-attempt state while
    a guarded fetch proceeds. No network calls or writes to request state.
    """
    path = Path(PROBE_STATE if path is None else path)
    lock_path = path.with_name(path.name + ".lock")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CrossPathProbeBlocked("Probe state directory unavailable") from exc
    try:
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            try:
                locked = os.fstat(lock.fileno())
                current = os.stat(lock_path)
                if locked.st_ino != current.st_ino or locked.st_dev != current.st_dev:
                    raise CrossPathProbeBlocked("Probe lock replaced; fetch blocked")
                status = check_probe_state(path)
                yield status
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise CrossPathProbeBlocked("Probe lock unavailable; fetch blocked") from exc


def guard_production_fetch(func):
    """Enforce probe gate at the HTTP-client function boundary."""
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        with hold_probe_gate():
            return func(*args, **kwargs)
    return wrapped
