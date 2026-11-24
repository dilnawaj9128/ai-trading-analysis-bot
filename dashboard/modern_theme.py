"""Presentation-only styling and plain-language help for Streamlit pages."""
import streamlit as st


CSS = """
<style>
:root {color-scheme: light;}
.stApp {background: linear-gradient(155deg, #f6f9fe 0%, #f9fbff 50%, #f0f5ff 100%); color: #14243b;}
[data-testid="stHeader"] {background: rgba(246,249,254,.85);}
[data-testid="stSidebar"] {background: #10233c;}
[data-testid="stSidebar"] * {color: #ecf2ff !important;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] * {color: #dce8fb !important;}
[data-testid="stSidebar"] a:hover {background: rgba(255,255,255,.12); border-radius: 10px;}
.block-container {padding-top: 2rem; max-width: 1360px;}
h1,h2,h3 {color: #14243b; letter-spacing: -.025em;}
h1 {font-weight: 750 !important;}
[data-testid="stMetric"] {background: #fff; border: 1px solid #e2eaf6; border-radius: 16px; padding: 18px; box-shadow: 0 6px 22px rgba(29,66,118,.06);}
[data-testid="stMetricLabel"] {color: #526784;}
[data-testid="stMetricValue"] {color: #112747; font-weight: 740;}
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {background:#fff; border: 1px solid #e1e9f5; border-radius: 14px; padding: 5px;}
.stButton > button[kind="primary"] {background:#2366e8; border:0; border-radius:11px; font-weight:650;}
.stButton > button, [data-testid="stDownloadButton"] button {border-radius:11px;}
[data-testid="stAlert"] {border-radius:12px;}
div[data-testid="stExpander"] {border:1px solid #e0e8f3; border-radius:12px; background:#fff;}
.modern-hero {padding:24px 28px; background:linear-gradient(115deg,#112a50,#2452a3); border-radius:19px; color:#fff; margin:0 0 18px; box-shadow:0 14px 30px rgba(30,65,130,.12);}
.modern-hero h2 {color:#fff!important; font-size:1.6rem; margin:0 0 9px;}
.modern-hero p {color:#e3edff; margin:0; line-height:1.65;}
.modern-kicker {color:#a7d1ff; text-transform:uppercase; letter-spacing:.13em; font-size:.74rem; font-weight:750; margin-bottom:8px;}
@media (max-width:700px) {.modern-hero {padding:19px;} .block-container {padding-top:1.2rem;}}
</style>
"""


def apply_modern_theme():
    """Only CSS; no network, credentials or request authorizations."""
    st.markdown(CSS, unsafe_allow_html=True)


def show_research_hero():
    st.markdown(
        '<div class="modern-hero">'
        '<div class="modern-kicker">AI Trading Research • Analysis only</div>'
        '<h2>Understand the market, one chart at a time</h2>'
        '<p>Study historical prices, indicators and 15-minute outcomes. '
        'Live requests remain blocked unless the existing API safety guard permits them. '
        'No broker orders are placed.</p></div>',
        unsafe_allow_html=True,
    )


def show_quick_links():
    st.subheader("Where should I start?")
    cols = st.columns(3)
    links = [
        ("📊 Offline Analysis", "pages/5_Offline_Market_Analysis.py",
         "Charts, indicators and historical outcomes — no API credits"),
        ("⚙️ Market Settings", "pages/2_Market_Configuration.py",
         "Choose symbol, timeframe and 15-minute observation"),
        ("📡 Live Monitor", "pages/4_Auto_Live_Monitor.py",
         "Shows data only when the existing authorization guard allows it"),
    ]
    for col, (label, target, detail) in zip(cols, links):
        with col:
            st.page_link(target, label=label, width="stretch")
            st.caption(detail)
