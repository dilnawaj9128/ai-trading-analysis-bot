"""Explicit local demo notifications. Never fetch or trade."""

from datetime import datetime, timezone

from notifications.result_notifications import (
    DEFAULT_DB,
    record_analysis_notification,
)


def create_demo_alert(*, enabled, db_path=DEFAULT_DB):
    if type(enabled) is not bool:
        raise ValueError("enabled must be boolean")

    if not enabled:
        return {
            "created": False,
            "reason": "DISABLED",
        }

    return record_analysis_notification(
        symbol="EUR/USD",
        timeframe="1min",
        candle_timestamp=datetime.now(timezone.utc).isoformat(),
        signal="NO TRADE",
        expiry_minutes=15,
        source="DEMO",
        enabled=True,
        db_path=db_path,
    )
