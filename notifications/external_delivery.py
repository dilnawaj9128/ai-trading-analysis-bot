"""Opt-in Telegram/email research notifications. No broker execution."""

import os
import smtplib
from email.message import EmailMessage

import requests

from notifications.preferences import load_notification_enabled


def _on(name):
    return os.getenv(name, "").strip().lower() == "true"


def _message(record):
    if (
        not isinstance(record, dict)
        or record.get("source") != "LIVE_RESEARCH"
        or record.get("signal") != "NO TRADE"
    ):
        raise ValueError("Only LIVE_RESEARCH NO TRADE alerts allowed")

    symbol = record.get("symbol")
    timeframe = record.get("timeframe")
    timestamp = record.get("candle_timestamp")
    expiry = record.get("expiry_minutes")

    if not all(isinstance(v, str) and v.strip()
               for v in (symbol, timeframe, timestamp)):
        raise ValueError("Invalid notification metadata")

    if timeframe not in {"1min", "5min", "15min"}:
        raise ValueError("Invalid timeframe")

    if type(expiry) is not int or expiry not in (1, 5, 15):
        raise ValueError("Invalid expiry")

    return (
        "AI Trading Analysis Bot\n"
        "Research status: NO TRADE\n"
        f"Market: {symbol}\n"
        f"Timeframe: {timeframe}\n"
        f"Observation: {timestamp}\n"
        f"Expiry setting: {expiry} minutes\n\n"
        "Analysis only. Feed/broker parity unverified. "
        "No trading recommendation or execution."
    )


def deliver_external_notification(record, *, preference_path=None):
    """Attempt delivery only with explicit per-channel opt-in.

    Invoked only after a NEW local analysis event is recorded.
    Does not fetch market data or execute trades.
    """
    if preference_path is None:
        enabled = load_notification_enabled()
    else:
        enabled = load_notification_enabled(preference_path)

    if not enabled:
        return {"telegram": "DISABLED", "email": "DISABLED"}

    telegram_enabled = _on("TRADING_ALERTS_TELEGRAM_ENABLED")
    email_enabled = _on("TRADING_ALERTS_EMAIL_ENABLED")

    if not telegram_enabled and not email_enabled:
        return {"telegram": "DISABLED", "email": "DISABLED"}

    message = _message(record)
    result = {"telegram": "DISABLED", "email": "DISABLED"}

    if telegram_enabled:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        if not token or not chat_id:
            result["telegram"] = "NOT_CONFIGURED"
        else:
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "disable_web_page_preview": True,
                    },
                    timeout=10,
                )
                response.raise_for_status()
                payload = response.json()
                result["telegram"] = (
                    "SENT" if payload.get("ok") is True else "FAILED"
                )
            except (requests.RequestException, ValueError):
                # Do not display token-containing URLs or responses.
                result["telegram"] = "FAILED"

    if email_enabled:
        host = os.getenv("SMTP_HOST", "")
        username = os.getenv("SMTP_USERNAME", "")
        password = os.getenv("SMTP_PASSWORD", "")
        recipient = os.getenv("ALERT_EMAIL_TO", "")

        try:
            port = int(os.getenv("SMTP_PORT", "465"))
        except ValueError:
            port = 0

        if (
            not all((host, username, password, recipient))
            or not 1 <= port <= 65535
            or any("\n" in v or "\r" in v for v in (username, recipient))
        ):
            result["email"] = "NOT_CONFIGURED"
        else:
            email = EmailMessage()
            email["From"] = username
            email["To"] = recipient
            email["Subject"] = "AI Trading Bot — Research Notification"
            email.set_content(message)

            try:
                with smtplib.SMTP_SSL(
                    host, port, timeout=10
                ) as smtp:
                    smtp.login(username, password)
                    smtp.send_message(email)
                result["email"] = "SENT"
            except (OSError, smtplib.SMTPException, ValueError):
                result["email"] = "FAILED"

    return result
