"""Consent-bound EUR/USD real data monitoring; no directional trading signals."""
import os
from pathlib import Path
from datetime import datetime,timezone
import streamlit as st
import plotly.graph_objects as go
from dotenv import load_dotenv
from dashboard.real_data_mode import fetch_real_data_once, analyze_frame
from dashboard.real_data_history import save_capture,load_history,resample_history,history_health
from dashboard.real_data_monitor import allow_attempt,fresh_observation_gate,manual_request_cooldown,MAX_ATTEMPTS

st.set_page_config(page_title='EUR/USD — Real Data',page_icon='📊',layout='wide')
st.title('📊 EUR/USD — Verified-candle Research Monitor')
st.caption('Twelve Data EUR/USD · completed 1-minute candles · indicators only · no trading signals or broker orders')
st.warning('Provider feed mode and Quotex broker price parity remain UNVERIFIED. Data-quality PASS is not provenance verification.')

for name,default in [('rdm_running',False),('rdm_attempts',0),('rdm_last_req',None),('rdm_latest',None),('rdm_error',None),('rdm_last_save',None),('rdm_manual_attempts',0),('rdm_last_manual_attempt',None)]:
    if name not in st.session_state:
        st.session_state[name]=default

interval=st.selectbox('Automatic fetch cadence (minutes)',[1,3,5],index=2,key='rdm_cadence')
view=st.selectbox('Chart timeframe (aggregated locally; no additional API calls)',[1,3,5],index=0,key='rdm_view')
consent=st.checkbox('I approve each manually initiated fetch and, separately, up to 3 monitored attempts per Start (maximum 2 accounted API requests per attempt).',key='rdm_monitor_approval')
st.caption('Manual Fetch can be used repeatedly across the session; it does NOT have the Auto Monitor 3-attempt cap. Each click still requires approval, a 60-second local cooldown, and passing the provider quota/credit authorization guard. This is NOT unlimited API quota.')
a,b,c=st.columns(3)
start=a.button('▶ Start limited monitoring',disabled=not consent or st.session_state.rdm_running)
stop=b.button('■ Stop monitoring',disabled=not st.session_state.rdm_running)
manual=c.button('Fetch once (approval required)',disabled=not consent or st.session_state.rdm_running)
if stop:
    st.session_state.rdm_running=False
if start:
    st.session_state.rdm_running=True
    st.session_state.rdm_attempts=0
    st.session_state.rdm_last_req=None
if not consent:
    st.session_state.rdm_running=False


def fetch_store(*, is_manual=False):
    # Keep manual usage separate from the three-attempt automatic-monitor cap.
    # Count before any HTTP; failed attempts are never retried automatically.
    if is_manual:
        st.session_state.rdm_manual_attempts+=1
        st.session_state.rdm_last_manual_attempt=datetime.now(timezone.utc).isoformat()
    else:
        st.session_state.rdm_attempts+=1
        st.session_state.rdm_last_req=datetime.now(timezone.utc).isoformat()
    load_dotenv(dotenv_path=Path.cwd()/'.env',override=False)
    key=os.environ.get('TWELVE_DATA_API_KEY')
    try:
        result=fetch_real_data_once(approved=True,api_key=key)
        saved=save_capture(result['frame'])
        st.session_state.rdm_latest=result
        st.session_state.rdm_last_save=saved
        st.session_state.rdm_error=None
    except Exception as exc:
        st.session_state.rdm_running=False
        # Avoid raw provider errors which could expose secrets.
        st.session_state.rdm_error=type(exc).__name__

if manual and consent:
    gate=manual_request_cooldown(st.session_state.rdm_last_manual_attempt)
    if gate['allowed']:
        fetch_store(is_manual=True)
    else:
        st.warning(f"Manual fetch cooldown: {gate['retry_after_seconds']}s left. No HTTP request sent.")

# Fragment triggers only while the browser page is mounted. A server restart
# resets approval and monitoring state. No unattended daemon, no auto-retry.
@st.fragment(run_every='15s')
def bounded_monitor():
    if not st.session_state.rdm_running:
        return
    if not allow_attempt(active=True,consent=st.session_state.rdm_monitor_approval,
                         attempts=st.session_state.rdm_attempts):
        st.session_state.rdm_running=False
        return
    if fresh_observation_gate(st.session_state.rdm_last_req,st.session_state.rdm_cadence):
        fetch_store()
        if st.session_state.rdm_attempts >= MAX_ATTEMPTS:
            st.session_state.rdm_running=False
        st.rerun(scope='app')

bounded_monitor()
st.caption(f"Monitor: {'ON' if st.session_state.rdm_running else 'OFF'} · auto attempts this Start: {st.session_state.rdm_attempts}/{MAX_ATTEMPTS} · manual attempts this session: {st.session_state.rdm_manual_attempts} · auto-stop on failure or cap")
if st.session_state.rdm_error:
    st.error('Fetch or validation blocked ('+st.session_state.rdm_error+'). Monitoring stopped; inspect local credit journals before another approval.')
if st.session_state.rdm_last_save:
    st.success('Validated candles persisted: '+str(st.session_state.rdm_last_save))

history=load_history()
health=history_health(history)
q=st.session_state.rdm_latest['quality'] if st.session_state.rdm_latest else None
c1,c2,c3,c4=st.columns(4)
c1.metric('Stored unique 1-min candles',health['rows'])
c2.metric('Historical missing minutes',health['missing_minutes'])
c3.metric('Current fetch quality',q['quality'] if q else 'NOT FETCHED')
c4.metric('Age at last fetch',f"{q['age_seconds']:.0f}s" if q else 'N/A')
st.caption('Latest persisted candle: '+str(health['last_open_utc']))
if q and q['stale']:
    st.warning('Last saved in-memory snapshot is stale; it is not a current live reading.')

if not history.empty:
    chart=resample_history(history,minutes=view)
    if not chart.empty:
        from indicators import calculate_indicators
        plotted=calculate_indicators(chart.copy()) if len(chart)>=60 else chart
        fig=go.Figure()
        fig.add_trace(go.Candlestick(x=chart.timestamp,open=chart.Open,high=chart.High,
                                    low=chart.Low,close=chart.Close,name='EUR/USD OHLC'))
        for name in ('EMA_20','EMA_50'):
            if name in plotted.columns:
                fig.add_trace(go.Scatter(x=chart.timestamp,y=plotted[name],mode='lines',name=name))
        fig.update_layout(title=f'Completed EUR/USD candles · {view} min view',height=480,
                          xaxis_rangeslider_visible=False)
        st.plotly_chart(fig,width='stretch')
    st.subheader('Stored market history (latest 50 candles)')
    st.dataframe(chart.tail(50),hide_index=True,width='stretch')
else:
    st.info('No persisted history yet. Approve an authenticated fetch to begin.')

if st.session_state.rdm_latest:
    st.subheader('Latest completed candle indicators')
    st.json({k:round(v,8) for k,v in st.session_state.rdm_latest['indicators'].items()})
st.caption('Analysis-only. No trading signals, no orders. Data quality is distinct from broker parity.')
