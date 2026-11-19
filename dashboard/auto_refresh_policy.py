"""Pure policy for an explicitly enabled, bounded Streamlit refresh session.

No imports from Streamlit, no provider calls and no disk mutations.
"""
from datetime import datetime, timedelta, timezone

MAX_CALLS = 3
MAX_SESSION_MINUTES = 60
MIN_INTERVAL_MINUTES = 3


def _utc(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("A timezone-aware datetime is required")
    return now.astimezone(timezone.utc)


def start_auto_refresh(*, now, minutes, approved):
    if approved is not True:
        raise ValueError("Explicit approval for a bounded auto session required")
    if type(minutes) is not int or minutes not in (3, 5, 15):
        raise ValueError("Supported intervals: 3, 5 or 15 minutes")
    t = _utc(now)
    return {
        "active": True,
        "interval_minutes": minutes,
        "attempts": 0,
        "started_at": t.isoformat(),
        "next_due_at": (t + timedelta(minutes=minutes)).isoformat(),
        "status": "ARMED",
    }


def due_for_refresh(state, *, now):
    t = _utc(now)
    if (type(state) is not dict or state.get("active") is not True
            or state.get("status") != "ARMED"):
        return False
    interval = state.get("interval_minutes")
    count = state.get("attempts")
    if type(interval) is not int or interval not in (3, 5, 15):
        return False
    if type(count) is not int or count < 0 or count >= MAX_CALLS:
        return False
    try:
        started = datetime.fromisoformat(state["started_at"])
        next_due = datetime.fromisoformat(state["next_due_at"])
        started = _utc(started)
        next_due = _utc(next_due)
    except (KeyError, TypeError, ValueError):
        return False
    # Clock reversal and expiration never authorize a request.
    if t < started or t >= started + timedelta(minutes=MAX_SESSION_MINUTES):
        return False
    if next_due < started + timedelta(minutes=interval):
        return False
    return t >= next_due


def finish_attempt(state, *, now, successful):
    """Mark an attempt before returning to the UI. No network operations."""
    t = _utc(now)
    if type(state) is not dict or state.get("active") is not True:
        raise ValueError("No active refresh session")
    count = state["attempts"]
    if type(count) is not int or not 0 <= count < MAX_CALLS:
        raise ValueError("Invalid attempt count")
    out = dict(state)
    out["attempts"] = count + 1
    if successful is not True or out["attempts"] >= MAX_CALLS:
        out["active"] = False
        out["status"] = "DONE" if successful is True else "STOPPED_AFTER_ERROR"
    else:
        out["next_due_at"] = (
            t + timedelta(minutes=out["interval_minutes"])
        ).isoformat()
        out["status"] = "ARMED"
    return out
