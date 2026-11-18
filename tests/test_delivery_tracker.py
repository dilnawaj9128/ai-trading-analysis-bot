from unittest.mock import patch

from notifications.delivery_tracker import (
    deliver_once, get_delivery_history,
)
from notifications.preferences import save_notification_enabled


RECORD = {
    "symbol": "EUR/USD",
    "timeframe": "1min",
    "candle_timestamp": "2026-11-18T10:00:00Z",
    "expiry_minutes": 15,
    "signal": "NO TRADE",
    "source": "LIVE_RESEARCH",
}


def test_first_delivery_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_ALERTS_TELEGRAM_ENABLED", "true")
    prefs = tmp_path / "prefs.json"
    db = tmp_path / "delivery.db"
    save_notification_enabled(True, prefs)

    with patch(
        "notifications.delivery_tracker.deliver_external_notification",
        return_value={"telegram": "SENT", "email": "DISABLED"},
    ):
        result = deliver_once(
            RECORD, db_path=db, preference_path=prefs
        )

    assert result["telegram"] == "SENT"
    assert get_delivery_history(db_path=db)[0]["telegram_status"] == "SENT"


def test_duplicate_never_sent_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_ALERTS_TELEGRAM_ENABLED", "true")
    prefs = tmp_path / "prefs.json"
    db = tmp_path / "delivery.db"
    save_notification_enabled(True, prefs)

    with patch(
        "notifications.delivery_tracker.deliver_external_notification",
        return_value={"telegram": "SENT", "email": "DISABLED"},
    ) as send:
        deliver_once(RECORD, db_path=db, preference_path=prefs)
        result = deliver_once(RECORD, db_path=db, preference_path=prefs)

    assert send.call_count == 1
    assert result["telegram"] == "DUPLICATE"


def test_disabled_does_not_send(tmp_path):
    prefs = tmp_path / "prefs.json"
    db = tmp_path / "delivery.db"
    save_notification_enabled(False, prefs)

    result = deliver_once(
        RECORD, db_path=db, preference_path=prefs
    )

    assert result["telegram"] == "DISABLED"
    assert not db.exists()


def test_demo_rejected(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setenv("TRADING_ALERTS_TELEGRAM_ENABLED", "true")
    prefs = tmp_path / "prefs.json"
    save_notification_enabled(True, prefs)

    with pytest.raises(ValueError):
        deliver_once(
            {**RECORD, "source": "DEMO"},
            db_path=tmp_path / "delivery.db",
            preference_path=prefs,
        )
