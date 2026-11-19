import json
from datetime import datetime, timezone, timedelta
from scripts.probe_recovery_report import inspect


def save(path, status='UNCERTAIN'):
    path.write_text(json.dumps({'version': 1, 'attempts': [{
        'status': status, 'started_at': datetime.now(timezone.utc).isoformat()}]}))


def test_missing_history_blocks(tmp_path):
    result = inspect(probe_path=tmp_path/'none.json', csv_path=tmp_path/'x.csv')
    assert result['status'] == 'BLOCKED'
    assert result['request_allowed'] is False


def test_uncertain_no_evidence_never_reconciles(tmp_path):
    path = tmp_path/'history.json'
    save(path)
    before = path.read_bytes()
    result = inspect(probe_path=path, csv_path=tmp_path/'nonexistent.csv')
    assert result['status'] == 'UNCERTAIN'
    assert not result['reconciled'] and not result['request_allowed']
    assert result['csv_modified_after_attempt'] == 'MISSING_OR_UNREADABLE'
    assert path.read_bytes() == before


def test_verified_still_does_not_authorize(tmp_path):
    path = tmp_path/'history.json'
    save(path, 'VERIFIED')
    result = inspect(probe_path=path)
    assert result['status'] == 'VERIFIED'
    assert result['request_allowed'] is False


def test_corrupted_file_blocks(tmp_path):
    path = tmp_path/'history.json'
    path.write_text('{')
    assert inspect(probe_path=path)['status'] == 'BLOCKED'


def test_mtime_after_attempt_is_not_reconciliation(tmp_path):
    path = tmp_path/'history.json'
    save(path)
    csv = tmp_path/'candles.csv'
    csv.write_text('saved')
    result = inspect(probe_path=path, csv_path=csv)
    assert result['csv_modified_after_attempt'] is True
    assert result['reconciled'] is False


def test_symlink_history_not_trusted(tmp_path):
    original = tmp_path/'original.json'
    save(original)
    alias = tmp_path/'alias.json'
    alias.symlink_to(original)
    assert inspect(probe_path=alias)['status'] == 'BLOCKED'
