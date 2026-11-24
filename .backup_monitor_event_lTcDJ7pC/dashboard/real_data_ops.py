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
