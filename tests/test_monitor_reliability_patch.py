from datetime import datetime, timedelta, timezone
from dashboard.monitor_reliability import due_for_auto_fetch, begin_attempt, end_attempt
from pathlib import Path
import ast
import pytest

BASE = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def due(**kw):
    defaults=dict(running=True,consent=True,attempts=0,in_progress=False,
        last_attempt_utc=None,cadence_minutes=5,now=BASE)
    defaults.update(kw)
    return due_for_auto_fetch(**defaults)


def test_first_due_and_regular_cadence():
    assert due()
    stamp=BASE.isoformat()
    assert not due(last_attempt_utc=stamp,now=BASE+timedelta(seconds=299))
    assert due(last_attempt_utc=stamp,now=BASE+timedelta(seconds=300))

@pytest.mark.parametrize('flag', ['running','consent'])
def test_consent_and_active_required(flag):
    assert not due(**{flag:False})

@pytest.mark.parametrize('n', [3,4,100])
def test_hard_auto_cap(n):
    assert not due(attempts=n)


def test_double_call_blocked():
    assert not due(in_progress=True)


def test_clock_rollback_fails_closed():
    assert not due(last_attempt_utc=(BASE+timedelta(seconds=5)).isoformat())

@pytest.mark.parametrize('minutes', [-1,0,2,60,'5'])
def test_invalid_interval(minutes):
    with pytest.raises(ValueError): due(cadence_minutes=minutes)


def test_non_utc_cadence_normalization():
    ist = timezone(timedelta(hours=5,minutes=30))
    assert due(last_attempt_utc=BASE.astimezone(ist).isoformat(),now=BASE+timedelta(minutes=5))


def test_request_counted_before_http_and_single_entry():
    s={'rdm_monitor_approval':True,'rdm_running':True,'rdm_attempts':0,'rdm_fetch_in_progress':False}
    assert begin_attempt(s,now=BASE)
    assert s['rdm_attempts']==1
    assert not begin_attempt(s,now=BASE)
    assert s['rdm_attempts']==1
    end_attempt(s,success=True)
    assert not s['rdm_fetch_in_progress'] and s['rdm_running']


def test_stop_on_failure():
    s={'rdm_monitor_approval':True,'rdm_running':True,'rdm_attempts':0}
    assert begin_attempt(s,now=BASE)
    end_attempt(s,success=False)
    assert not s['rdm_running'] and not s['rdm_fetch_in_progress']


def test_third_attempt_auto_stops():
    s={'rdm_monitor_approval':True,'rdm_running':True,'rdm_attempts':2}
    assert begin_attempt(s,now=BASE)
    end_attempt(s,success=True)
    assert s['rdm_attempts']==3 and not s['rdm_running']
    assert not begin_attempt(s,now=BASE)


def test_manual_separate_from_auto_cap():
    s={'rdm_monitor_approval':True,'rdm_running':False,'rdm_attempts':3}
    assert begin_attempt(s,manual=True,now=BASE)
    assert s['rdm_manual_attempts']==1 and s['rdm_attempts']==3
    end_attempt(s,success=True)


def test_no_approval_no_fetch():
    s={'rdm_monitor_approval':False,'rdm_running':True,'rdm_attempts':0}
    assert not begin_attempt(s,now=BASE)
    assert s['rdm_attempts']==0


def test_dashboard_still_research_only():
    s=Path(__file__).parent.parent/'dashboard/pages/10_Real_Data_Mode.py'
    source=s.read_text()
    ast.parse(source)
    assert 'no trading signals or broker orders' in source
    assert 'run_every=\'15s\'' in source
    assert 'end_attempt(st.session_state, success=success)' in source
    assert 'fetch_real_data_once(approved=True' in source
    assert 'credit_repair_preview' in source
