"""Modern beginner-friendly overview. No real market requests."""
import streamlit as st

from dashboard.modern_theme import apply_modern_theme, show_quick_links, show_research_hero
from market_data.credit_dashboard_status import get_credit_dashboard_status

st.set_page_config(page_title="Start Here | Market Research", page_icon="🧭", layout="wide")
apply_modern_theme()
show_research_hero()

st.title("Start Here")
st.caption("A simple guide to your AI Trading Analysis Bot")

try:
    credit = get_credit_dashboard_status()
except (OSError, ValueError, TypeError):
    credit = {"status": "UNKNOWN", "credits_left": None, "message": "Credit status unavailable"}

c1, c2, c3 = st.columns(3)
c1.metric("Research mode", "OFFLINE READY")
c2.metric("Live API credits", credit.get("status", "UNKNOWN"))
c3.metric("Trade execution", "DISABLED")
if credit.get("status") != "READY":
    st.warning("Live data is currently blocked or unconfirmed. Offline analysis remains available. Do not bypass the credit guard.")
else:
    st.info("Credit snapshot meets the display threshold; actual authorization is checked separately for each request.")

show_quick_links()
st.divider()
st.subheader("Understand the dashboard")
with st.expander("What do UP, DOWN and NO TRADE mean?", expanded=True):
    st.write("**UP / DOWN** describe directions only when evidence and strategy safety gates allow it. **NO TRADE** means the strategy does not provide an eligible directional result; it does not prove a losing trade was avoided.")
with st.expander("What do the indicators mean?"):
    st.write("**EMA:** recent price trend. **RSI:** relative momentum. **MACD:** momentum comparison. **ATR:** recent price-range volatility. Patterns describe past candles, not guaranteed future outcomes.")
with st.expander("What is a 15-minute outcome?"):
    st.write("It compares a historical observation price with the price 15 minutes later. The outcome is known after the fact; it is not a live prediction or broker win rate.")
with st.expander("Why can live data be blocked?"):
    st.write("Unknown or stale provider credits, incomplete authorization, or unverified feed status may stop fetching. These safeguards protect the API quota and preserve research integrity.")
st.caption("All information is research-only. Historical data is not validated against broker execution prices.")
