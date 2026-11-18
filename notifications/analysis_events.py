"""Record eligible analysis events without fetching or trading."""

from pathlib import Path

import pandas as pd

from notifications.preferences import (
    DEFAULT_PATH,
    load_notification_enabled,
)
from notifications.result_notifications import (
    DEFAULT_DB,
    record_analysis_notification,
)


def record_monitor_analysis_event(
    *,
    config,
    frame,
    fetch_status,
    signal_readiness,
    stale,
    gaps,
    preferences_path=DEFAULT_PATH,
    db_path=DEFAULT_DB,
):
    """Record only a newly fetched, eligible research result."""

    def skipped(reason):
        return {
            "created": False,
            "reason": reason,
            "analysis_only": True,
            "execution_enabled": False,
        }

    if not load_notification_enabled(preferences_path):
        return skipped("DISABLED")

    if fetch_status != "SUCCESS":
        return skipped("NOT_NEW_FETCH")

    if stale or gaps != 0:
        return skipped("DATA_NOT_READY")

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return skipped("INVALID_FRAME")

    if not isinstance(signal_readiness, dict):
        return skipped("INVALID_READINESS")

    # Fail closed: unverified feeds cannot generate UP/DOWN
    # notifications. Only research NO TRADE is supported here.
    if signal_readiness.get("signal") != "NO TRADE":
        return skipped("DIRECTIONAL_NOTIFICATION_BLOCKED")

    if signal_readiness.get("expiry_minutes") != config.expiry_minutes:
        return skipped("EXPIRY_MISMATCH")

    if "timestamp" not in frame.columns:
        return skipped("INVALID_FRAME")

    stamp = pd.Timestamp(frame["timestamp"].iloc[-1])

    if pd.isna(stamp) or stamp.tzinfo is None:
        return skipped("INVALID_TIMESTAMP")

    return record_analysis_notification(
        symbol=config.symbol,
        timeframe=config.timeframe,
        candle_timestamp=stamp.isoformat(),
        signal="NO TRADE",
        expiry_minutes=config.expiry_minutes,
        enabled=True,
        source="LIVE_RESEARCH",
        db_path=Path(db_path),
    )
