from notifications.result_notifications import (
    record_analysis_notification,
    get_notification_history,
)


STAMP = "2026-11-18T10:00:00Z"


def notify(tmp_path, **kwargs):
    values = {
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "candle_timestamp": STAMP,
        "signal": "UP",
        "db_path": tmp_path / "notifications.db",
    }
    values.update(kwargs)
    return record_analysis_notification(**values)


def test_new_notification(tmp_path):
    result = notify(tmp_path)
    assert result["created"] is True
    assert result["execution_enabled"] is False


def test_duplicate_suppression(tmp_path):
    notify(tmp_path)
    result = notify(tmp_path)
    assert result["created"] is False
    assert result["reason"] == "DUPLICATE"


def test_disabled_notifications(tmp_path):
    result = notify(tmp_path, enabled=False)
    assert result["reason"] == "DISABLED"
    assert get_notification_history(
        db_path=tmp_path / "notifications.db"
    ) == []


def test_history_persists(tmp_path):
    notify(tmp_path)

    history = get_notification_history(
        db_path=tmp_path / "notifications.db"
    )

    assert len(history) == 1
    assert history[0]["signal"] == "UP"


def test_no_trade_supported(tmp_path):
    result = notify(tmp_path, signal="NO TRADE")
    assert result["created"] is True
