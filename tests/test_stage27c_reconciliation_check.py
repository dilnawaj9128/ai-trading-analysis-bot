import json
from datetime import datetime, timezone, timedelta
from scripts.probe_reconciliation_check import create_checklist, main


def _history(path, status='UNCERTAIN', started=None):
    started = started or datetime(2026, 11, 19, 13, 6, 33, tzinfo=timezone.utc)
    path.write_text(json.dumps({'version': 1, 'attempts': [{'id': 'offline-test',
         'started_at': started.isoformat(), 'status': status}]}))
    return started


def test_missing_evidence_never_authorizes(tmp_path):
    r = create_checklist(probe_path=tmp_path/'missing', csv_path=tmp_path/'missing.csv')
    assert r['request_allowed'] is False and r['reconciled'] is False
    assert r['probe_status'] == 'BLOCKED'


def test_uncertain_report_requires_review_and_no_write(tmp_path):
    p = tmp_path/'probe.json'; t = _history(p)
    before = p.read_bytes()
    r = create_checklist(probe_path=p, csv_path=tmp_path/'none.csv')
    assert r['probe_status'] == 'UNCERTAIN'
    assert r['review_window_utc'][0] == (t-timedelta(minutes=5)).isoformat()
    assert r['review_window_utc'][1] == (t+timedelta(minutes=10)).isoformat()
    assert r['manual_review_required'] and not r['request_allowed']
    assert p.read_bytes() == before


def test_csv_updated_after_attempt_is_not_proof(tmp_path):
    p = tmp_path/'probe.json'; _history(p)
    c = tmp_path/'candles.csv'; c.write_text('nothing secret')
    r = create_checklist(probe_path=p, csv_path=c)
    assert r['csv_evidence']['modified_after_attempt'] is True
    assert r['reconciled'] is False and r['request_allowed'] is False


def test_symlink_probe_is_not_accepted(tmp_path):
    p = tmp_path/'real'; _history(p)
    alias = tmp_path/'alias'; alias.symlink_to(p)
    r = create_checklist(probe_path=alias)
    assert r['probe_status'] == 'BLOCKED'
    assert r['request_allowed'] is False


def test_verified_does_not_bypass_normal_guards(tmp_path):
    p = tmp_path/'probe.json'; _history(p, 'VERIFIED')
    r = create_checklist(probe_path=p)
    assert r['probe_status'] == 'VERIFIED'
    assert r['request_allowed'] is False
    assert 'normal cooldown' in r['next_action']


def test_cli_no_secret_or_transport(tmp_path, capsys):
    p = tmp_path/'probe.json'; _history(p)
    main(['--probe', str(p), '--csv', str(tmp_path/'none')])
    out = capsys.readouterr().out
    assert 'No network calls' in out
    assert 'request_allowed: False' in out
