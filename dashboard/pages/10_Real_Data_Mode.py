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
from dashboard.real_data_ops import append_event, recent_events, operational_status, monitor_event_audit
from dashboard.monitor_reliability import due_for_auto_fetch, begin_attempt, end_attempt, MAX_AUTO_ATTEMPTS

st.set_page_config(page_title='EUR/USD — Real Data',page_icon='📊',layout='wide')
st.title('📊 EUR/USD — Verified-candle Research Monitor')
st.caption('Twelve Data EUR/USD · completed 1-minute candles · indicators only · no trading signals or broker orders')
st.warning('Provider feed mode and Quotex broker price parity remain UNVERIFIED. Data-quality PASS is not provenance verification.')

for name,default in [('rdm_running',False),('rdm_attempts',0),('rdm_last_req',None),('rdm_latest',None),('rdm_error',None),('rdm_last_save',None),('rdm_manual_attempts',0),('rdm_last_manual_attempt',None),('rdm_fetch_in_progress',False)]:
    if name not in st.session_state:
        st.session_state[name]=default

interval=st.selectbox('Automatic fetch cadence (minutes)',[1,3,5],index=2,key='rdm_cadence')
view=st.selectbox('Chart timeframe (aggregated locally; no additional API calls)',[1,3,5],index=0,key='rdm_view')
consent=st.checkbox('I approve each manually initiated fetch and, separately, up to 3 monitored attempts per Start (maximum 2 accounted API requests per attempt).',key='rdm_monitor_approval')
st.caption('Manual Fetch can be used repeatedly across the session; it does NOT have the Auto Monitor 3-attempt cap. Each click still requires approval, a 60-second local cooldown, and passing the provider quota/credit authorization guard. This is NOT unlimited API quota.')

# No-network repair path: only the existing receipt-bound reconciler may settle.
# Deliberately never reset the local ledger or assume old unknown calls succeeded.
from dashboard.credit_repair_control import credit_repair_preview, reconcile_receipts_safely
repair_preview = credit_repair_preview()
if repair_preview['fetch_headroom_blocked']:
    st.warning('Provider fetch paused: '+repair_preview['message']+
               ' Existing stored candles remain available for historical analysis.')
if st.button('Reconcile verified credit receipts (offline, 0 API requests)', key='rdm_reconcile_receipts'):
    repair_result = reconcile_receipts_safely()
    if repair_result['ok']:
        st.success('Verified receipt reconciliation finished; '+
                   str(repair_result['outstanding_reserved'])+' credits remain reserved. '+
                   'Final API authorization may still block.')
    else:
        st.error('Credit reconciliation blocked safely: '+repair_result['reason']+
                 '. No reservations were reset.')
    st.rerun()

a,b,c=st.columns(3)
start=a.button('▶ Start limited monitoring',disabled=not consent or st.session_state.rdm_running or repair_preview['fetch_headroom_blocked'])
stop=b.button('■ Stop monitoring',disabled=not st.session_state.rdm_running)
manual=c.button('Fetch once (approval required)',disabled=not consent or st.session_state.rdm_running or repair_preview['fetch_headroom_blocked'])
if stop:
    st.session_state.rdm_running=False
    append_event("MONITOR_STOPPED")
if start:
    append_event("MONITOR_STARTED")
    st.session_state.rdm_running=True
    st.session_state.rdm_attempts=0
    st.session_state.rdm_last_req=None
if not consent or repair_preview['fetch_headroom_blocked']:
    if st.session_state.rdm_running:
        st.session_state.rdm_running=False
        append_event("MONITOR_STOPPED")


def fetch_store(*, is_manual=False):
    # Session-level re-entrancy guard; provider quota guard stays authoritative.
    if not begin_attempt(st.session_state, manual=is_manual):
        return
    success = False
    error_class = None
    try:
        append_event("FETCH_STARTED")
        load_dotenv(dotenv_path=Path.cwd()/'.env', override=False)
        key = os.environ.get('TWELVE_DATA_API_KEY')
        result = fetch_real_data_once(approved=True, api_key=key)
        saved = save_capture(result['frame'])
        st.session_state.rdm_latest = result
        st.session_state.rdm_last_save = saved
        st.session_state.rdm_error = None
        success = True
    except Exception as exc:
        # Never expose raw provider response, credentials or exception message.
        error_class = type(exc).__name__
        st.session_state.rdm_error = error_class
    finally:
        end_attempt(st.session_state, success=success)
        try:
            if success:
                append_event("FETCH_SUCCEEDED")
            else:
                append_event("FETCH_BLOCKED", error_class=error_class or "MonitorFailure")
                append_event("MONITOR_STOPPED")
            if success and st.session_state.rdm_attempts >= MAX_AUTO_ATTEMPTS:
                append_event("MONITOR_STOPPED")
        except (OSError, ValueError, RuntimeError):
            st.session_state.rdm_error = st.session_state.rdm_error or "MonitoringAuditUnavailable"
            st.session_state.rdm_running = False

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
    if not st.session_state.rdm_running or credit_repair_preview()['fetch_headroom_blocked']:
        if st.session_state.rdm_running:
            st.session_state.rdm_running=False
            append_event("MONITOR_STOPPED")
        return
    if not due_for_auto_fetch(
        running=st.session_state.rdm_running,
        consent=st.session_state.rdm_monitor_approval,
        attempts=st.session_state.rdm_attempts,
        in_progress=st.session_state.rdm_fetch_in_progress,
        last_attempt_utc=st.session_state.rdm_last_req,
        cadence_minutes=st.session_state.rdm_cadence,
    ):
        if st.session_state.rdm_attempts >= MAX_AUTO_ATTEMPTS or not st.session_state.rdm_monitor_approval:
            if st.session_state.rdm_running:
                st.session_state.rdm_running = False
                append_event("MONITOR_STOPPED")
        return
    fetch_store()
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
st.subheader('Operational reliability · read-only')
ops = operational_status()
if ops['history_stale_over_3min']:
    st.warning('Persisted candles are historical/stale, not a live market quotation.')
st.caption('Age since last persisted close: ' +
           ('N/A' if ops['age_since_last_close_seconds'] is None else
            str(ops['age_since_last_close_seconds']) + ' seconds'))
try:
    from dashboard.credit_renewal_diagnostics import credit_renewal_readiness
    preflight = credit_renewal_readiness()
    st.caption('Credit snapshot preflight: '+preflight['status']+
               ' · '+preflight['reason'])
    st.caption('Preflight is read-only; the final provider authorization guard is authoritative.')
except (OSError, ValueError, KeyError, TypeError):
    st.caption('Credit preflight unavailable. Do not assume provider quota is available.')
# Read-only quota arithmetic: snapshot freshness alone does not authorize requests.
from dashboard.twelve_data_readiness import readiness as twelve_data_readiness
api_readiness = twelve_data_readiness()
st.subheader('Twelve Data API readiness · local accounting')
st.caption('Provider snapshot is a past observation, not a promise of live quota.')
st.caption('Status: ' + api_readiness['status'] + ' · ' + api_readiness['reason'])
if api_readiness['provider_credits_left'] is not None:
    st.caption('Last observed credits left: ' + str(api_readiness['provider_credits_left']) +
               ' · outstanding reservations: ' + str(api_readiness['outstanding_reserved']) +
               ' · conservative headroom: ' + str(api_readiness['conservative_headroom']))
st.caption('This panel makes zero HTTP calls and never overrides the final authorization guard.')

audit_summary = monitor_event_audit()
if audit_summary['unmatched_fetch_starts'] or audit_summary['unmatched_monitor_starts']:
    st.caption('Historical audit: '+str(audit_summary['unmatched_fetch_starts'])+' fetch start(s) without an outcome and '+str(audit_summary['unmatched_monitor_starts'])+' monitor start(s) without a stop event; these are UNKNOWN, not verified failures/successes.')
events = recent_events(limit=12)
if events:
    with st.expander('Recent monitoring events (no keys or raw provider errors)'):
        st.dataframe(events, width='stretch', hide_index=True)
st.caption('Analysis-only. No trading signals, no orders. Data quality is distinct from broker parity.')
