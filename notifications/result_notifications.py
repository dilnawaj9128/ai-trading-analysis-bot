"""Persistent local research notifications. No network or trading."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/notifications/analysis_notifications.db")

SIGNALS = {"UP", "DOWN", "NO TRADE"}

SOURCES = {
    "DEMO",
    "LIVE_RESEARCH",
    "HISTORICAL_RESEARCH",
    "LEGACY_UNCLASSIFIED",
}


def _ensure_schema(conn):
    """Create table or migrate old history without deleting records."""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            candle_timestamp TEXT NOT NULL,
            signal TEXT NOT NULL,
            expiry_minutes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'LEGACY_UNCLASSIFIED',
            UNIQUE (
                symbol,
                timeframe,
                candle_timestamp,
                expiry_minutes
            )
        )
    """)

    columns = {
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(analysis_notifications)"
        )
    }

    if "source" not in columns:
        conn.execute("""
            ALTER TABLE analysis_notifications
            ADD COLUMN source TEXT NOT NULL
            DEFAULT 'LEGACY_UNCLASSIFIED'
        """)


def record_analysis_notification(
    *,
    symbol,
    timeframe,
    candle_timestamp,
    signal,
    expiry_minutes=15,
    enabled=True,
    source="LEGACY_UNCLASSIFIED",
    db_path=DEFAULT_DB,
):
    if type(enabled) is not bool:
        raise ValueError("enabled must be boolean")

    if not enabled:
        return {"created": False, "reason": "DISABLED"}

    if signal not in SIGNALS:
        raise ValueError("Invalid signal")

    if source not in SOURCES:
        raise ValueError("Invalid notification source")

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Invalid symbol")

    if timeframe not in {"1min", "5min", "15min"}:
        raise ValueError("Invalid timeframe")

    if (
        type(expiry_minutes) is not int
        or expiry_minutes not in (1, 5, 15)
    ):
        raise ValueError("Invalid expiry")

    stamp = datetime.fromisoformat(
        str(candle_timestamp).replace("Z", "+00:00")
    )

    if stamp.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")

    stamp = stamp.astimezone(timezone.utc).isoformat()

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path, timeout=10) as conn:
        _ensure_schema(conn)

        cursor = conn.execute("""
            INSERT OR IGNORE INTO analysis_notifications (
                symbol,
                timeframe,
                candle_timestamp,
                signal,
                expiry_minutes,
                created_at,
                source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol.strip(),
            timeframe,
            stamp,
            signal,
            expiry_minutes,
            datetime.now(timezone.utc).isoformat(),
            source,
        ))

        created = cursor.rowcount == 1

    return {
        "created": created,
        "reason": "NEW_RESULT" if created else "DUPLICATE",
        "signal": signal,
        "source": source,
        "analysis_only": True,
        "execution_enabled": False,
    }


def get_notification_history(*, db_path=DEFAULT_DB, limit=50):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Invalid history limit")

    path = Path(db_path)

    if not path.exists():
        return []

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)

        rows = conn.execute("""
            SELECT symbol, timeframe, candle_timestamp,
                   signal, expiry_minutes, source, created_at
            FROM analysis_notifications
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [dict(row) for row in rows]
