"""Detect new local research notifications. No network requests."""


def notification_key(record):
    required = (
        "symbol",
        "timeframe",
        "candle_timestamp",
        "expiry_minutes",
        "source",
    )

    if not isinstance(record, dict):
        raise ValueError("Notification record must be a dictionary")

    if any(key not in record for key in required):
        raise ValueError("Incomplete notification record")

    return tuple(record[key] for key in required)


def detect_new_alerts(history, seen_keys, *, enabled):
    """Return updated seen keys and newly eligible alerts.

    Caller initializes seen_keys from existing history on page load.
    """

    if type(enabled) is not bool:
        raise ValueError("Invalid notification preference")

    if not isinstance(history, list):
        raise ValueError("History must be a list")

    seen = set(seen_keys)
    alerts = []

    for record in history:
        key = notification_key(record)

        if key in seen:
            continue

        seen.add(key)

        if (
            enabled
            and record.get("source") == "LIVE_RESEARCH"
            and record.get("signal") == "NO TRADE"
        ):
            alerts.append(record)

    return seen, alerts
