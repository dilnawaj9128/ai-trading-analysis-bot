"""Persistent, at-most-once Telegram delivery attempts."""

import hashlib
import json
import sqlite3
from pathlib import Path

from notifications.external_delivery import deliver_external_notification
from notifications.preferences import load_notification_enabled

DEFAULT_DB = Path("data/notifications/delivery_status.db")


def event_key(record):
    if (
        not isinstance(record, dict)
        or record.get("source") != "LIVE_RESEARCH"
        or record.get("signal") != "NO TRADE"
    ):
        raise ValueError("Only LIVE_RESEARCH NO TRADE events supported")

    keys = (
        "symbol", "timeframe", "candle_timestamp",
        "expiry_minutes", "signal", "source",
    )

    if any(key not in record for key in keys):
        raise ValueError("Incomplete analysis event")

    payload = {key: record[key] for key in keys}

    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def deliver_once(record, *, db_path=DEFAULT_DB, preference_path=None):
    """Reserve event before sending; never automatically retry."""
    import os

    if preference_path is None:
        enabled = load_notification_enabled()
    else:
        enabled = load_notification_enabled(preference_path)

    if not enabled:
        return {"telegram": "DISABLED", "email": "DISABLED"}

    # Only Telegram is tracked by this stage.
    if os.getenv(
        "TRADING_ALERTS_TELEGRAM_ENABLED", ""
    ).strip().lower() != "true":
        return {"telegram": "DISABLED", "email": "DISABLED"}

    key = event_key(record)
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS delivery_attempts (
                event_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                candle_timestamp TEXT NOT NULL,
                telegram_status TEXT NOT NULL,
                email_status TEXT NOT NULL
            )
        """)

        cursor = conn.execute("""
            INSERT OR IGNORE INTO delivery_attempts
            (event_key, symbol, signal, candle_timestamp,
             telegram_status, email_status)
            VALUES (?, ?, ?, ?, 'PENDING', 'DISABLED')
        """, (
            key,
            record["symbol"],
            record["signal"],
            record["candle_timestamp"],
        ))

        if cursor.rowcount != 1:
            return {
                "telegram": "DUPLICATE",
                "email": "DISABLED",
            }

    # Reservation was committed before any external request.
    try:
        result = deliver_external_notification(
            record, preference_path=preference_path
        )
    except Exception:
        # Unknown outcome: do not resend automatically.
        result = {"telegram": "UNCERTAIN", "email": "UNCERTAIN"}

    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("""
            UPDATE delivery_attempts
            SET telegram_status=?, email_status=?
            WHERE event_key=? AND telegram_status='PENDING'
        """, (
            result["telegram"],
            result["email"],
            key,
        ))

    return result


def get_delivery_history(*, db_path=DEFAULT_DB, limit=50):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Invalid limit")

    path = Path(db_path)
    if not path.exists():
        return []

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT symbol, signal, candle_timestamp,
                   telegram_status, email_status
            FROM delivery_attempts
            ORDER BY rowid DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [dict(row) for row in rows]
