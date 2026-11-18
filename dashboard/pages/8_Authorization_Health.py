"""Read-only market authorization health dashboard."""

import streamlit as st

from analysis.authorization_health import get_authorization_health

st.set_page_config(
    page_title="Authorization Health",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Authorization Health")
st.caption(
    "Read-only research diagnostics. No API requests, "
    "credit reservations or trading execution."
)

report = get_authorization_health()

a, b, c = st.columns(3)

a.metric("Provider Credits", report["provider_status"])
b.metric("Authorization Evidence", report["evidence_status"])
c.metric(
    "Recovery Marker",
    "PRESENT" if report["recovery_marker"] else "ABSENT",
)

st.divider()

a, b, c = st.columns(3)

a.metric("Pending Requests", report["pending"])
b.metric("Uncertain Requests", report["uncertain"])
c.metric(
    "Reserved Credits",
    report["reserved_credits"]
    if report["reserved_credits"] is not None
    else "Unverified",
)

st.subheader("Authorization Status")

st.warning(
    "This dashboard does not authorize live requests. "
    "Actual fetching requires the complete provider-credit, "
    "local-budget and recovery checks."
)

st.write("**Diagnostic reason:**", report["reason"])

st.info(
    "Trading execution is disabled. "
    "NO TRADE remains the safe result when market-data "
    "verification is unavailable."
)

if st.button("Refresh Local Status"):
    st.rerun()
