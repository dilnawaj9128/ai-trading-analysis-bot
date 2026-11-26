"""No-network diagnostics and minimal, credential-free operational event log.

Data-quality checks do not establish feed provenance or broker parity.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from dashboard.real_data_history import DEFAULT_DB, load_history, history_health

DEFAULT_EVENTS_DB = Path("data/real_market/eurusd_monitor_events.sqlite3")

EVENT_TYPES = frozenset({"FETCH_STARTED", "FETCH_SUCCEEDED", "FETCH_BLOCKED", "MONITOR_STARTED", "MONITOR_STOPPED"})


def append_event(event: str, *, db_path=DEFAULT_EVENTS_DB, error_class: str | None = None):
    """Persist an allowlisted event and exception class; never store exception messages/API keys."""
    if event not in EVENT_TYPES:
        raise ValueError("Unrecognized monitor event")
    if error_class is not None and (not isinstance(error_class, str) or
            not error_class.isidentifier() or len(error_class) > 80):
        raise ValueError("Unsafe error class")
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=15) as con:
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("""CREATE TABLE IF NOT EXISTS monitor_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time_utc TEXT NOT NULL,
            event_type TEXT NOT NULL,
            error_class TEXT
        )""")
        con.execute("INSERT INTO monitor_events (event_time_utc,event_type,error_class) VALUES (?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), event, error_class))


def recent_events(db_path=DEFAULT_EVENTS_DB, limit=15):
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("Event limit out of range")
    path = Path(db_path)
    if not path.exists():
        return []
    with sqlite3.connect(path) as con:
        found = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monitor_events'").fetchone()
        if found is None:
            return []
        rows = con.execute("""SELECT event_time_utc,event_type,error_class
                 FROM monitor_events ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    return [{"utc": u, "event": e, "error_class": err} for u,e,err in rows]


def operational_status(*, db_path=DEFAULT_DB, now=None, history_limit=2000):
    """Pure local inspection. No provider API, no quota use, no secret reading."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Aware clock required")
    history = load_history(db_path, limit=history_limit)
    health = history_health(history)
    last = health["last_open_utc"]
    age = None
    if last:
        last_time = datetime.fromisoformat(last)
        age = max(0, int((now.astimezone(timezone.utc) - last_time.astimezone(timezone.utc)).total_seconds() - 60))
    return {
        "stored_candles_in_read_window": health["rows"],
        "missing_minutes_in_read_window": health["missing_minutes"],
        "latest_open_utc": last,
        "age_since_last_close_seconds": age,
        "history_stale_over_3min": age is None or age > 180,
        "history_scope": f"latest_{history_limit}_stored_rows",
        "feed_mode_verified": False,
        "quotex_parity_verified": False,
        "provider_credit_authorized": "NOT_CHECKED",
        "broker_orders": 0,
    }


def monitor_event_audit(*, db_path=DEFAULT_EVENTS_DB):
    """Read-only historical event-balance audit; an unmatched start is UNKNOWN.

    Does not inspect or modify credits, requests, keys or broker data.
    Events currently have no run IDs; this is only aggregate evidence.
    """
    path = Path(db_path)
    empty = {"fetch_started": 0, "fetch_succeeded": 0, "fetch_blocked": 0,
             "unmatched_fetch_starts": 0, "monitor_started": 0,
             "monitor_stopped": 0, "unmatched_monitor_starts": 0,
             "audit_scope": "all_events_aggregate_no_run_ids"}
    if not path.is_file():
        return empty
    with sqlite3.connect(path, timeout=15) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='monitor_events'").fetchone()
        if not exists:
            return empty
        rows = con.execute("SELECT event_type FROM monitor_events ORDER BY id").fetchall()
    result = dict(empty)
    unmatched_fetch = 0
    unmatched_monitor = 0
    mapping = {"FETCH_STARTED": "fetch_started", "FETCH_SUCCEEDED": "fetch_succeeded",
               "FETCH_BLOCKED": "fetch_blocked", "MONITOR_STARTED": "monitor_started",
               "MONITOR_STOPPED": "monitor_stopped"}
    for (event,) in rows:
        field = mapping.get(event)
        if field is None:
            continue
        result[field] += 1
        if event == "FETCH_STARTED":
            unmatched_fetch += 1
        elif event in ("FETCH_SUCCEEDED", "FETCH_BLOCKED") and unmatched_fetch:
            unmatched_fetch -= 1
        elif event == "MONITOR_STARTED":
            unmatched_monitor += 1
        elif event == "MONITOR_STOPPED" and unmatched_monitor:
            unmatched_monitor -= 1
    result["unmatched_fetch_starts"] = unmatched_fetch
    result["unmatched_monitor_starts"] = unmatched_monitor
    return result
