"""Read-only preflight for explicitly approved Twelve Data research sessions.

The durable provider probe remains the final authority at the moment of fetch.
This module never reserves credits, mutates probe history, or sends HTTP.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math

PROBE_HISTORY = Path("data/api_usage/approved_research_probe.json")
COOLDOWN_SECONDS = 180


def inspect_probe_readiness(*, now=None, path=PROBE_HISTORY):
    """Return READY, WAITING_FOR_COOLDOWN, or BLOCKED without side effects.

    The last attempt must be VERIFIED. Unknown/corrupt state is always BLOCKED.
    This is an advisory check; probe_once() independently enforces its lock.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")
    now = now.astimezone(timezone.utc)
    path = Path(path)
    if not path.is_file():
        # A missing file is only potentially eligible. probe_once rechecks it.
        if path.exists() or path.is_symlink():
            return {"status": "BLOCKED", "seconds_left": None, "reason": "Invalid probe path"}
        return {"status": "READY", "seconds_left": 0, "reason": "No previous probe history"}

    try:
        history = json.loads(path.read_text(encoding="utf-8"))
        if type(history) is not dict or history.get("version") != 1:
            raise ValueError("Invalid history schema")
        attempts = history.get("attempts")
        if type(attempts) is not list:
            raise ValueError("Invalid attempt list")
        if not attempts:
            return {"status": "READY", "seconds_left": 0, "reason": "No previous probe attempts"}
        entry = attempts[-1]
        if type(entry) is not dict or entry.get("status") != "VERIFIED":
            return {"status": "BLOCKED", "seconds_left": None, "reason": "Previous probe unresolved; manual review required"}
        started_at = datetime.fromisoformat(entry["started_at"])
        if started_at.tzinfo is None:
            raise ValueError("Naive timestamp")
        started_at = started_at.astimezone(timezone.utc)
        if started_at > now:
            raise ValueError("Clock moved backwards")
        remaining = (started_at + timedelta(seconds=COOLDOWN_SECONDS) - now).total_seconds()
        if remaining > 0:
            return {"status": "WAITING_FOR_COOLDOWN", "seconds_left": math.ceil(remaining),
                    "reason": "Last verified probe is within the 3-minute cooldown"}
        return {"status": "READY", "seconds_left": 0, "reason": "Probe cooldown satisfied"}
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return {"status": "BLOCKED", "seconds_left": None,
                "reason": "Probe history invalid or unreadable; manual review required"}


def due_for_live_refresh(state, *, now):
    """Stage 27: allow one immediate first tick; reuse Stage 26 thereafter."""
    from dashboard.auto_refresh_policy import due_for_refresh

    if type(state) is not dict or state.get("active") is not True:
        return False
    if state.get("status") != "ARMED":
        return False
    if type(state.get("attempts")) is not int:
        return False
    if state["attempts"] != 0:
        return due_for_refresh(state, now=now)
    if state.get("interval_minutes") not in (3, 5, 15):
        return False
    try:
        started = datetime.fromisoformat(state["started_at"])
        due = datetime.fromisoformat(state["next_due_at"])
        if started.tzinfo is None or due.tzinfo is None:
            return False
        current = now.astimezone(timezone.utc)
        started = started.astimezone(timezone.utc)
        due = due.astimezone(timezone.utc)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return (
        current >= started
        and current >= due
        and current < started + timedelta(minutes=60)
    )
