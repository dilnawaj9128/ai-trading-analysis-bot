from types import SimpleNamespace

import pandas as pd

from notifications.preferences import save_notification_enabled
from notifications.analysis_events import record_monitor_analysis_event
from notifications.result_notifications import get_notification_history


def setup(tmp_path, *, enabled=True):
    prefs = tmp_path / "preferences.json"
    db = tmp_path / "notifications.db"

    save_notification_enabled(enabled, prefs)

    config = SimpleNamespace(
        symbol="EUR/USD",
        timeframe="1min",
        expiry_minutes=15,
    )

    frame = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-11-18T10:00:00Z")
        ]
    })

    return {
        "config": config,
        "frame": frame,
        "fetch_status": "SUCCESS",
        "signal_readiness": {
            "signal": "NO TRADE",
            "expiry_minutes": 15,
        },
        "stale": False,
        "gaps": 0,
        "preferences_path": prefs,
        "db_path": db,
    }


def test_new_result_recorded(tmp_path):
    args = setup(tmp_path)
    result = record_monitor_analysis_event(**args)
    assert result["created"] is True


def test_duplicate_not_recorded(tmp_path):
    args = setup(tmp_path)
    record_monitor_analysis_event(**args)

    result = record_monitor_analysis_event(**args)
    assert result["reason"] == "DUPLICATE"


def test_disabled_preference_blocks(tmp_path):
    args = setup(tmp_path, enabled=False)
    result = record_monitor_analysis_event(**args)

    assert result["reason"] == "DISABLED"
    assert get_notification_history(
        db_path=args["db_path"]
    ) == []


def test_waiting_does_not_notify(tmp_path):
    args = setup(tmp_path)
    args["fetch_status"] = "WAITING"

    result = record_monitor_analysis_event(**args)
    assert result["created"] is False


def test_unverified_directional_result_blocked(tmp_path):
    args = setup(tmp_path)
    args["signal_readiness"]["signal"] = "UP"

    result = record_monitor_analysis_event(**args)
    assert result["reason"] == "DIRECTIONAL_NOTIFICATION_BLOCKED"


def test_stale_data_blocked(tmp_path):
    args = setup(tmp_path)
    args["stale"] = True

    result = record_monitor_analysis_event(**args)
    assert result["reason"] == "DATA_NOT_READY"
