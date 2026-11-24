import sqlite3
from dashboard.real_data_ops import append_event, monitor_event_audit


def test_unmatched_event_is_unknown_not_success(tmp_path):
    db = tmp_path / 'events.sqlite3'
    append_event('MONITOR_STARTED', db_path=db)
    append_event('FETCH_STARTED', db_path=db)
    audit = monitor_event_audit(db_path=db)
    assert audit['unmatched_fetch_starts'] == 1
    assert audit['unmatched_monitor_starts'] == 1
    assert audit['fetch_succeeded'] == 0


def test_closed_events_audit(tmp_path):
    db = tmp_path / 'events.sqlite3'
    for event in ('MONITOR_STARTED','FETCH_STARTED','FETCH_SUCCEEDED','MONITOR_STOPPED'):
        append_event(event, db_path=db)
    result = monitor_event_audit(db_path=db)
    assert result['unmatched_fetch_starts'] == 0
    assert result['unmatched_monitor_starts'] == 0
    assert result['fetch_succeeded'] == 1


def test_missing_db_no_creation(tmp_path):
    db = tmp_path/'missing.sqlite3'
    assert monitor_event_audit(db_path=db)['unmatched_fetch_starts'] == 0
    assert not db.exists()


def test_extra_terminal_events_never_negative(tmp_path):
    db=tmp_path/'events.sqlite3'
    append_event('MONITOR_STOPPED', db_path=db)
    append_event('FETCH_BLOCKED', db_path=db, error_class='TimeoutError')
    r=monitor_event_audit(db_path=db)
    assert r['unmatched_fetch_starts'] == 0
    assert r['unmatched_monitor_starts'] == 0
