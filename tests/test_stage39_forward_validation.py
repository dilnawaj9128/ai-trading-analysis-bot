import json
from datetime import datetime, timedelta, timezone
import pytest
from scripts.run_stage39_forward_validation import freeze, observe, report, load_run

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def blocked(*args, **kwargs):
    return {'status': 'BLOCKED', 'signal': 'NO TRADE',
            'reason': 'Latest provider attempt unresolved', 'provider_attested': False}


def test_freeze_and_report(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    r = report(p)
    assert r['observations'] == 0 and r['win_rate'] is None
    assert r['strategy_status'] == 'UNVALIDATED_RESEARCH'


def test_no_overwrite_frozen_plan(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    with pytest.raises(ValueError, match='already exists'):
        freeze(p, now=NOW)


def test_unresolved_provenance_recorded_as_blocked(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    o = observe(p, now=NOW + timedelta(minutes=1), evaluator=blocked)
    assert o['signal'] == 'NO TRADE'
    assert o['outcome'] == 'NOT_EVALUATED'
    assert report(p)['blocked'] == 1
    assert report(p)['settled'] == 0


def test_no_pre_freeze_observation(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    with pytest.raises(ValueError, match='strictly after'):
        observe(p, now=NOW, evaluator=blocked)


def test_duplicate_timestamp_rejected(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    observe(p, now=NOW + timedelta(minutes=1), evaluator=blocked)
    with pytest.raises(ValueError, match='chronological'):
        observe(p, now=NOW + timedelta(minutes=1), evaluator=blocked)


def test_unverified_direction_rejected(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    def bogus(*args, **kwargs):
        return {'status': 'VALID', 'signal': 'UP', 'provider_attested': False}
    with pytest.raises(ValueError, match='provider evidence'):
        observe(p, now=NOW + timedelta(minutes=1), evaluator=bogus)
    assert report(p)['observations'] == 0


def test_invalid_blocked_direction_rejected(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    def bogus(*args, **kwargs):
        return {'status': 'BLOCKED', 'signal': 'DOWN', 'provider_attested': False}
    with pytest.raises(ValueError, match='Blocked observation'):
        observe(p, now=NOW + timedelta(minutes=1), evaluator=bogus)


def test_identical_csv_replay_rejected(tmp_path):
    p = tmp_path / 'run.json'
    csv = tmp_path / 'data.csv'
    csv.write_text('some snapshot', encoding='utf8')
    freeze(p, now=NOW)
    observe(p, csv=csv, now=NOW + timedelta(minutes=1), evaluator=blocked)
    with pytest.raises(ValueError, match='Identical CSV'):
        observe(p, csv=csv, now=NOW + timedelta(minutes=2), evaluator=blocked)


def test_no_real_win_rate_from_blocked_log(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    observe(p, now=NOW + timedelta(minutes=1), evaluator=blocked)
    r = report(p)
    assert r['win_rate'] is None and r['settled'] == 0


def test_tampered_safety_flag_rejected(tmp_path):
    p = tmp_path / 'run.json'
    freeze(p, now=NOW)
    data = json.loads(p.read_text())
    data['execution_enabled'] = True
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='altered'):
        load_run(p)
