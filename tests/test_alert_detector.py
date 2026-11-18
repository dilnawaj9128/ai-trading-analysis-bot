from notifications.alert_detector import (
    detect_new_alerts,
    notification_key,
)


def record(source="LIVE_RESEARCH", stamp="2026-11-18T10:00:00Z"):
    return {
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "candle_timestamp": stamp,
        "expiry_minutes": 15,
        "signal": "NO TRADE",
        "source": source,
    }


def test_new_live_alert():
    seen, alerts = detect_new_alerts(
        [record()], set(), enabled=True
    )
    assert len(alerts) == 1
    assert len(seen) == 1


def test_duplicate_alert_blocked():
    item = record()
    seen, _ = detect_new_alerts(
        [item], set(), enabled=True
    )

    _, alerts = detect_new_alerts(
        [item], seen, enabled=True
    )
    assert alerts == []


def test_disabled_blocks_alerts():
    _, alerts = detect_new_alerts(
        [record()], set(), enabled=False
    )
    assert alerts == []


def test_demo_not_alerted():
    _, alerts = detect_new_alerts(
        [record(source="DEMO")],
        set(),
        enabled=True,
    )
    assert alerts == []


def test_legacy_not_alerted():
    _, alerts = detect_new_alerts(
        [record(source="LEGACY_UNCLASSIFIED")],
        set(),
        enabled=True,
    )
    assert alerts == []


def test_second_candle_creates_new_alert():
    first = record()
    seen = {notification_key(first)}

    second = record(stamp="2026-11-18T10:01:00Z")

    _, alerts = detect_new_alerts(
        [second, first], seen, enabled=True
    )

    assert len(alerts) == 1
    assert alerts[0]["candle_timestamp"] == second["candle_timestamp"]
