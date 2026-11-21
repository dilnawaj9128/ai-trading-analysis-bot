import sqlite3
"""Analysis notification dashboard — local only."""

import pandas as pd
import streamlit as st

from notifications.preferences import (
    load_notification_enabled,
    save_notification_enabled,
)
from notifications.result_notifications import (
    get_notification_history,
)

st.set_page_config(
    page_title="Analysis Notifications",
    page_icon="🔔",
    layout="wide",
)

st.title("🔔 Analysis Notifications")
st.caption(
    "Local history | Duplicate protection | Analysis only"
)

st.warning(
    "Notifications are not trading instructions. "
    "Live notification delivery is not yet connected."
)

try:
    current = load_notification_enabled()
except (OSError, ValueError) as exc:
    st.error(f"Notification settings unavailable: {exc}")
    st.stop()

enabled = st.toggle(
    "Enable notifications for future analysis integrations",
    value=current,
    help="Stores your preference. Does not start a live monitor.",
)

if enabled != current:
    try:
        save_notification_enabled(enabled)
        st.success("Notification preference saved.")
    except OSError as exc:
        st.error(f"Could not save preference: {exc}")
        st.stop()

st.subheader("Test Notifications")

st.caption(
    "Generate a labeled DEMO record. No real market data or API request."
)

if st.button("🔔 Send Test Alert", disabled=not enabled):
    from notifications.demo_alerts import create_demo_alert

    try:
        result = create_demo_alert(enabled=enabled)

        if result["created"]:
            st.toast("DEMO — Notification system test", icon="🔔")
            st.success("Demo notification saved to local history.")
        else:
            st.info(f"Test alert not created: {result['reason']}")

    except (OSError, ValueError) as exc:
        st.error(f"Demo notification failed: {exc}")

st.subheader("Notification Status")

a, b, c = st.columns(3)

a.metric("Preference", "ON" if enabled else "OFF")
from notifications.delivery_tracker import get_delivery_history

delivery_history = get_delivery_history(limit=1)

last_telegram_status = (
    delivery_history[0]["telegram_status"]
    if delivery_history
    else "No attempts"
)

b.metric("Last Telegram delivery", last_telegram_status)
c.metric("Trading execution", "Disabled")

st.divider()


# STAGE 22E — new research result alerts.
from notifications.alert_detector import (
    detect_new_alerts,
    notification_key,
)

@st.fragment(run_every="10s")
def notification_alert_panel():
    try:
        current_history = get_notification_history(limit=500)
        enabled_now = load_notification_enabled()
    except (OSError, ValueError, TypeError) as exc:
        st.warning(f"Alert monitoring unavailable: {exc}")
        return

    state_key = "stage22e_seen_notification_keys"

    # First visit: mark existing history as seen, without alerting.
    if state_key not in st.session_state:
        st.session_state[state_key] = {
            notification_key(item)
            for item in current_history
        }
        st.caption("Alert monitoring active for new research records.")
        return

    seen, alerts = detect_new_alerts(
        current_history,
        st.session_state[state_key],
        enabled=enabled_now,
    )

    st.session_state[state_key] = seen

    for item in alerts:
        st.toast(
            f"{item['symbol']} — New NO TRADE research status",
            icon="🔔",
        )

    st.caption(
        "Checking local notification history every 10 seconds. "
        "No market API requests."
    )


notification_alert_panel()

st.subheader("Telegram Delivery Status")

from notifications.delivery_tracker import get_delivery_history

try:
    delivery_history = get_delivery_history(limit=50)
except (OSError, ValueError, sqlite3.Error) as exc:
    st.warning(f"Delivery history unavailable: {exc}")
    delivery_history = []

if delivery_history:
    st.dataframe(
        pd.DataFrame(delivery_history),
        width="stretch",
        hide_index=True,
    )
else:
    st.info(
        "No tracked Telegram delivery attempts yet. "
        "Earlier manually sent messages are not included."
    )

st.caption(
    "SENT means Telegram API accepted the request. "
    "FAILED or PENDING attempts are not automatically retried."
)

st.subheader("Notification History")

try:
    history = get_notification_history(limit=100)
except (OSError, ValueError) as exc:
    st.error(f"Could not load notification history: {exc}")
    st.stop()

if not history:
    st.info(
        "No notifications recorded yet. "
        "New records will appear after the analysis pipeline "
        "is explicitly connected in a later stage."
    )
else:
    frame = pd.DataFrame(history)

    source_filter = st.selectbox(
        "Filter by source",
        [
            "ALL",
            "DEMO",
            "LIVE_RESEARCH",
            "HISTORICAL_RESEARCH",
            "LEGACY_UNCLASSIFIED",
        ],
    )

    if source_filter != "ALL":
        frame = frame.loc[frame["source"] == source_filter]

    signal_filter = st.selectbox(
        "Filter by signal",
        ["ALL", "UP", "DOWN", "NO TRADE"],
    )

    if signal_filter != "ALL":
        frame = frame.loc[
            frame["signal"] == signal_filter
        ]

    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
    )

    st.download_button(
        "Export history as CSV",
        data=frame.to_csv(index=False),
        file_name="analysis_notification_history.csv",
        mime="text/csv",
    )

st.divider()

st.info(
    "Local research notification recording is integrated. "
    "Browser alerts require an open monitoring session "
    "and a new authorized analysis result. "
    "External delivery remains disabled."
)
