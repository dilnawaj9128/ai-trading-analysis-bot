from unittest.mock import Mock, patch

from notifications.external_delivery import (
    deliver_external_notification,
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


def test_disabled_preference_blocks_delivery(tmp_path):
    prefs = tmp_path / "preferences.json"
    save_notification_enabled(False, prefs)

    with patch("requests.post") as post:
        result = deliver_external_notification(
            RECORD, preference_path=prefs
        )
        post.assert_not_called()

    assert result["telegram"] == "DISABLED"


def test_channels_default_off(tmp_path, monkeypatch):
    prefs = tmp_path / "preferences.json"
    save_notification_enabled(True, prefs)

    monkeypatch.delenv("TRADING_ALERTS_TELEGRAM_ENABLED", raising=False)
    monkeypatch.delenv("TRADING_ALERTS_EMAIL_ENABLED", raising=False)

    result = deliver_external_notification(
        RECORD, preference_path=prefs
    )

    assert result == {
        "telegram": "DISABLED",
        "email": "DISABLED",
    }


def test_unverified_direction_blocked(tmp_path, monkeypatch):
    prefs = tmp_path / "preferences.json"
    save_notification_enabled(True, prefs)

    monkeypatch.setenv("TRADING_ALERTS_TELEGRAM_ENABLED", "true")

    record = {**RECORD, "signal": "UP"}

    with patch("requests.post") as post:
        try:
            deliver_external_notification(
                record, preference_path=prefs
            )
            assert False, "Directional alert should be rejected"
        except ValueError:
            pass

        post.assert_not_called()


def test_demo_delivery_blocked(tmp_path, monkeypatch):
    prefs = tmp_path / "preferences.json"
    save_notification_enabled(True, prefs)

    monkeypatch.setenv("TRADING_ALERTS_TELEGRAM_ENABLED", "true")

    with patch("requests.post") as post:
        try:
            deliver_external_notification(
                {**RECORD, "source": "DEMO"},
                preference_path=prefs,
            )
            assert False, "Demo alert should be rejected"
        except ValueError:
            pass

        post.assert_not_called()


def test_telegram_success_mocked(tmp_path, monkeypatch):
    prefs = tmp_path / "preferences.json"
    save_notification_enabled(True, prefs)

    monkeypatch.setenv("TRADING_ALERTS_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TRADING_ALERTS_EMAIL_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    response = Mock()
    response.json.return_value = {"ok": True}
    response.raise_for_status.return_value = None

    with patch("requests.post", return_value=response) as post:
        result = deliver_external_notification(
            RECORD, preference_path=prefs
        )

    assert result["telegram"] == "SENT"
    post.assert_called_once()


def test_email_success_mocked(tmp_path, monkeypatch):
    prefs = tmp_path / "preferences.json"
    save_notification_enabled(True, prefs)

    monkeypatch.setenv("TRADING_ALERTS_TELEGRAM_ENABLED", "false")
    monkeypatch.setenv("TRADING_ALERTS_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_USERNAME", "bot@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "fake-password")
    monkeypatch.setenv("ALERT_EMAIL_TO", "user@example.test")

    with patch("smtplib.SMTP_SSL") as smtp:
        result = deliver_external_notification(
            RECORD, preference_path=prefs
        )

    assert result["email"] == "SENT"
    smtp.assert_called_once()
