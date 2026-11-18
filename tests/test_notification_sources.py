import sqlite3

import pytest

from notifications.result_notifications import (
    record_analysis_notification,
    get_notification_history,
)


def notify(path, **changes):
    arguments = {
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "candle_timestamp": "2026-11-18T10:00:00Z",
        "signal": "NO TRADE",
        "expiry_minutes": 15,
        "db_path": path,
    }
    arguments.update(changes)
    return record_analysis_notification(**arguments)


def test_demo_source_saved(tmp_path):
    path = tmp_path / "history.db"
    notify(path, source="DEMO")

    history = get_notification_history(db_path=path)
    assert history[0]["source"] == "DEMO"


def test_live_research_source_saved(tmp_path):
    path = tmp_path / "history.db"
    notify(path, source="LIVE_RESEARCH")

    history = get_notification_history(db_path=path)
    assert history[0]["source"] == "LIVE_RESEARCH"


def test_historical_source_saved(tmp_path):
    path = tmp_path / "history.db"
    notify(path, source="HISTORICAL_RESEARCH")

    assert get_notification_history(
        db_path=path
    )[0]["source"] == "HISTORICAL_RESEARCH"


def test_invalid_source_rejected(tmp_path):
    with pytest.raises(ValueError):
        notify(
            tmp_path / "history.db",
            source="VERIFIED_PROFIT",
        )


def test_old_database_migrated_without_data_loss(tmp_path):
    path = tmp_path / "old.db"

    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE analysis_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                candle_timestamp TEXT NOT NULL,
                signal TEXT NOT NULL,
                expiry_minutes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (
                    symbol, timeframe,
                    candle_timestamp, expiry_minutes
                )
            )
        """)

        conn.execute("""
            INSERT INTO analysis_notifications
            (symbol, timeframe, candle_timestamp,
             signal, expiry_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "EUR/USD", "1min",
            "2026-11-18T10:00:00+00:00",
            "NO TRADE", 15,
            "2026-11-18T10:01:00+00:00",
        ))

    history = get_notification_history(db_path=path)

    assert len(history) == 1
    assert history[0]["source"] == "LEGACY_UNCLASSIFIED"
