
"""Stage 7.3: conservative, research-only polling scheduler."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_data.twelve_data_client import (
    BudgetExceeded,
    MarketDataError,
    fetch_recent_candles,
)

POLLING_MINUTES = (1, 3, 5)
DEFAULT_POLLING_MINUTES = 3

# Global local-machine spacing, regardless of symbol or browser session.
MIN_REQUEST_SPACING_SECONDS = 60
ERROR_BACKOFF_SECONDS = 180

SCHEDULER_PATH = Path(
    "data/api_usage/live_monitor_scheduler.json"
)


def utc_now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _parse_time(value):
    if not value:
        return None

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise MarketDataError("Scheduler timestamp lacks timezone")

    return dt.astimezone(timezone.utc)


def _read_state(file):
    file.seek(0)
    raw = file.read()

    if not raw.strip():
        return {}

    try:
        state = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MarketDataError(
            "Scheduler state corrupted; polling blocked"
        ) from exc

    if not isinstance(state, dict):
        raise MarketDataError("Invalid scheduler state")

    return state


def _save_state(file, state):
    file.seek(0)
    file.truncate()
    json.dump(state, file, indent=2)
    file.flush()
    os.fsync(file.fileno())


def reserve_poll(
    *,
    interval_minutes=DEFAULT_POLLING_MINUTES,
    path=SCHEDULER_PATH,
    now=None,
):
    """Reserve one poll slot across local processes.

    Uses a persistent file lock and fails closed on invalid state.
    No network request happens here.
    """
    if (
        type(interval_minutes) is not int
        or interval_minutes not in POLLING_MINUTES
    ):
        raise ValueError("Polling must be 1, 3 or 5 minutes")

    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError("Polling time must have a timezone")

    now = now.astimezone(timezone.utc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a+", encoding="utf-8") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

        try:
            state = _read_state(file)

            last_attempt = _parse_time(
                state.get("last_attempt_utc")
            )
            next_allowed = _parse_time(
                state.get("next_allowed_utc")
            )

            if last_attempt and now < last_attempt:
                raise MarketDataError(
                    "System clock moved backwards; polling blocked"
                )

            if next_allowed and now < next_allowed:
                return {
                    "allowed": False,
                    "next_allowed_utc": _iso(next_allowed),
                    "reason": "Waiting for polling interval",
                }

            spacing = max(
                interval_minutes * 60,
                MIN_REQUEST_SPACING_SECONDS,
            )

            next_allowed = now + timedelta(
                seconds=spacing
            )

            state.update({
                "last_attempt_utc": _iso(now),
                "next_allowed_utc": _iso(next_allowed),
                "last_status": "RESERVED",
            })

            _save_state(file, state)

            return {
                "allowed": True,
                "next_allowed_utc": _iso(next_allowed),
                "reason": "Poll reserved",
            }
        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def record_poll_result(
    *,
    status,
    path=SCHEDULER_PATH,
    now=None,
):
    """Record outcome without shortening an existing cooldown."""

    if status not in ("SUCCESS", "ERROR", "BUDGET_BLOCKED"):
        raise ValueError("Invalid poll status")

    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError("Result time must have a timezone")

    now = now.astimezone(timezone.utc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a+", encoding="utf-8") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

        try:
            state = _read_state(file)

            if status != "SUCCESS":
                candidate = now + timedelta(
                    seconds=ERROR_BACKOFF_SECONDS
                )

                current = _parse_time(
                    state.get("next_allowed_utc")
                )

                if current is None or candidate > current:
                    state["next_allowed_utc"] = _iso(candidate)

            state["last_status"] = status
            state["last_result_utc"] = _iso(now)

            _save_state(file, state)
        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def read_monitor_state(path=SCHEDULER_PATH):
    """Read local scheduler status safely."""
    path = Path(path)

    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_SH)

        try:
            return _read_state(file)
        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def run_monitor_poll(
    config,
    *,
    interval_minutes=DEFAULT_POLLING_MINUTES,
    scheduler_path=SCHEDULER_PATH,
    fetcher=None,
    now=None,
):
    """Attempt one scheduled fetch.

    One local-machine request slot is shared by all configurations.
    The underlying client still enforces its own API budget.
    """
    now = now or utc_now()

    slot = reserve_poll(
        interval_minutes=interval_minutes,
        path=scheduler_path,
        now=now,
    )

    if not slot["allowed"]:
        return {
            "status": "WAITING",
            "reason": slot["reason"],
            "next_allowed_utc": slot["next_allowed_utc"],
            "result": None,
        }

    fetch = fetcher or fetch_recent_candles

    try:
        result = fetch(config)

    except BudgetExceeded:
        record_poll_result(
            status="BUDGET_BLOCKED",
            path=scheduler_path,
            now=now,
        )
        return {
            "status": "BUDGET_BLOCKED",
            "reason": "Local API budget exhausted",
            "result": None,
        }

    except MarketDataError as exc:
        record_poll_result(
            status="ERROR",
            path=scheduler_path,
            now=now,
        )
        return {
            "status": "ERROR",
            "reason": str(exc),
            "result": None,
        }

    except Exception:
        record_poll_result(
            status="ERROR",
            path=scheduler_path,
            now=now,
        )
        raise

    record_poll_result(
        status="SUCCESS",
        path=scheduler_path,
        now=now,
    )

    return {
        "status": "SUCCESS",
        "reason": "Market data fetched",
        "result": result,
    }

