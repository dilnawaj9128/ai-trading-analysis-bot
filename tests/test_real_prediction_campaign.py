"""Self-contained offline tests: no API credentials, network or broker access."""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from research import real_prediction_campaign as c


def candles(start, n=120):
    base = pd.Timestamp(start)
    times = pd.date_range(base, periods=n, freq='min', tz='UTC')
    close = [1.10 + i * 0.00001 for i in range(n)]
    return pd.DataFrame({'timestamp': times, 'Open': close, 'High': [v + 0.00002 for v in close],
                         'Low': [v - 0.00002 for v in close], 'Close': close})


def install_stubs(monkeypatch, frame):
    """Use existing Stage29 contract but synthetic candles for isolated tests."""
    r = types.ModuleType('research.stage29_backtest')
    r.load_candles = lambda path: frame.copy()
    r.existing_strategy_on_prefix = lambda prefix: 'UP'
    a = types.ModuleType('scripts.run_stage45_dataset_audit')
    a.parse_candles = lambda path: [{}] * len(frame)
    a.quality = lambda rows: {'continuous_one_minute_candles': True}
    monkeypatch.setitem(sys.modules, 'research.stage29_backtest', r)
    monkeypatch.setitem(sys.modules, 'scripts.run_stage45_dataset_audit', a)


def test_record_and_settle_exact_15m(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    original = candles(start, 120)
    install_stubs(monkeypatch, original)
    file = tmp_path / 'fresh.csv'; file.write_text('immutable fake source')
    now = start + timedelta(minutes=120, seconds=15)
    target, obs = c.observe(file, journal=tmp_path / 'journal', now=now)
    assert target.exists() and obs['research_hypothesis'] == 'UP'
    assert obs['live_trading_signal'] == 'NO TRADE'
    assert c.prospective_scorecard(tmp_path / 'journal')['counts']['WIN'] == 0
    with pytest.raises(ValueError, match='15-minute non-overlap'):
        c.observe(file, journal=tmp_path / 'journal', now=now)
    with pytest.raises(ValueError, match='not observable yet'):
        c.settle_one(target, file, journal=tmp_path / 'journal', now=now)
    later = candles(start, 136)
    install_stubs(monkeypatch, later)
    second = tmp_path / 'later.csv'; second.write_text('later immutable fake source')
    settlement, record = c.settle_one(target, second, journal=tmp_path / 'journal',
                                      now=start + timedelta(minutes=137))
    assert record['result'] == 'WIN'
    assert c.prospective_scorecard(tmp_path / 'journal')['counts']['WIN'] == 1
    assert c.prospective_scorecard(tmp_path / 'journal')['statistical_audit']['status'] == 'INSUFFICIENT_SAMPLE'
    with pytest.raises(FileExistsError):
        c.settle_one(target, second, journal=tmp_path / 'journal',
                     now=start + timedelta(minutes=137))


def test_stale_or_future_observation_blocks(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    install_stubs(monkeypatch, candles(start, 120))
    p = tmp_path / 'a.csv'; p.write_text('a')
    for now in [start + timedelta(minutes=119), start + timedelta(minutes=124)]:
        with pytest.raises(ValueError, match='stale|incomplete'):
            c.observe(p, journal=tmp_path / 'j', now=now)
    assert not list((tmp_path / 'j').glob('observations/*.json'))


def test_tampering_blocks_outcome(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    install_stubs(monkeypatch, candles(start, 120))
    file = tmp_path / 'in.csv'; file.write_text('a')
    target, _ = c.observe(file, journal=tmp_path / 'j', now=start + timedelta(minutes=120))
    doc = json.loads(target.read_text())
    doc['record']['research_hypothesis'] = 'DOWN'
    target.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='checksum'):
        c.settle_one(target, file, journal=tmp_path / 'j', now=start + timedelta(minutes=137))


def test_expiry_candle_required(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    install_stubs(monkeypatch, candles(start, 120))
    file = tmp_path / 'one.csv'; file.write_text('data')
    target, _ = c.observe(file, journal=tmp_path / 'j', now=start + timedelta(minutes=120))
    with pytest.raises(ValueError, match='Exact expiry candle'):
        c.settle_one(target, file, journal=tmp_path / 'j', now=start + timedelta(minutes=137))


def test_settlement_entry_mismatch_blocks(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    install_stubs(monkeypatch, candles(start, 120))
    file = tmp_path / 'one.csv'; file.write_text('data')
    target, _ = c.observe(file, journal=tmp_path / 'j', now=start + timedelta(minutes=120))
    later = candles(start, 136)
    later.loc[119, 'Close'] += 0.001
    install_stubs(monkeypatch, later)
    with pytest.raises(ValueError, match='entry reference'):
        c.settle_one(target, file, journal=tmp_path / 'j', now=start + timedelta(minutes=137))


def test_settlement_abstain(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    original = candles(start, 120)
    install_stubs(monkeypatch, original)
    sys.modules['research.stage29_backtest'].existing_strategy_on_prefix = lambda p: 'NO TRADE'
    file = tmp_path / 'one.csv'; file.write_text('data')
    target, _ = c.observe(file, journal=tmp_path / 'j', now=start + timedelta(minutes=120))
    install_stubs(monkeypatch, candles(start, 136))
    _, settlement = c.settle_one(target, file, journal=tmp_path / 'j', now=start + timedelta(minutes=137))
    assert settlement['result'] == 'ABSTAINED'
    counts = c.prospective_scorecard(tmp_path / 'j')['counts']
    assert counts['ABSTAINED'] == 1 and counts['WIN'] == 0


def test_no_fake_future_evidence(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    install_stubs(monkeypatch, candles(start, 136))
    p = tmp_path / 'a.csv'; p.write_text('data')
    # The 136th candle is not complete by this observation timestamp.
    with pytest.raises(ValueError):
        c.observe(p, journal=tmp_path / 'j', now=start + timedelta(minutes=120))


def test_dataset_duplicate_and_overlapping_detection(monkeypatch):
    def synthetic(p, payout):
        if str(p) in ('a', 'copy'):
            return {'dataset': str(p), 'source_sha256': 'a', 'first_candle_utc': '2026-01-01T00:00:00+00:00',
                    'last_candle_utc': '2026-01-01T01:00:00+00:00', 'wins': 1, 'losses': 0,
                    'nonpush': 1, 'net_units': 0.8}
        return {'dataset': 'b', 'source_sha256': 'b', 'first_candle_utc': '2026-01-01T00:30:00+00:00',
                'last_candle_utc': '2026-01-01T03:00:00+00:00', 'wins': 0, 'losses': 1,
                'nonpush': 1, 'net_units': -1.0}
    monkeypatch.setattr(c, 'historical_dataset', synthetic)
    r = c.historical_campaign(['a','copy','b'])
    assert len(r['datasets']) == 2
    assert len(r['rejected_datasets']) == 1
    assert r['overlapping_candle_ranges']
    assert not r['overall_descriptive_only']['safe_to_pool_as_independent']


def test_new_file_never_overwrites(tmp_path):
    path = tmp_path / 'file.json'
    c._new_file(path, {'a': 1})
    with pytest.raises(FileExistsError):
        c._new_file(path, {'a': 2})
    assert json.loads(path.read_text())['a'] == 1


def test_invalid_timezone():
    with pytest.raises(ValueError):
        c.utc('2026-11-20T00:00:00')


def test_no_api_or_broker_imports():
    import inspect
    text = inspect.getsource(c)
    assert 'requests.get(' not in text and 'httpx' not in text
    assert 'broker_orders' in text


def test_one_shot_requires_approval_before_imports():
    from scripts.run_real_prediction_live_once import capture_live_once
    with pytest.raises(ValueError, match='Explicit'):
        capture_live_once(api_key='not-a-real-key')
    with pytest.raises(ValueError, match='missing'):
        capture_live_once(api_key='', approved=True)


def test_live_cli_is_preview_only_by_default(capsys):
    from scripts.run_real_prediction_live_once import main
    assert main([]) == 0
    assert '0 HTTP' in capsys.readouterr().out


def test_one_shot_reuses_existing_verified_fetch_and_saves_csv(tmp_path, monkeypatch):
    import importlib
    from scripts import run_real_prediction_live_once as live
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    frame = candles(start, 120)
    calls = {'renew': 0, 'fetch': 0, 'settle': 0, 'observe': 0}
    names = {
        'market_data.verified_reservation_settlement': {'reconcile_verified_historical': lambda: None},
        'market_data.provider_credit_state': {'load_credit_state': lambda: object()},
        'market_data.verified_credit_renewal': {'renew_verified_credits_once': lambda **kw: calls.__setitem__('renew', calls['renew'] + 1)},
        'market_data.authorized_live_fetch': {'fetch_authorized_live_candles': None},
        'config.market_config': {'create_research_config': lambda *args: object()},
    }
    def fetch(*args, **kw):
        assert kw['settle_verified'] is True
        calls['fetch'] += 1
        return {'frame': frame, 'stale': False, 'gaps': 0}
    names['market_data.authorized_live_fetch']['fetch_authorized_live_candles'] = fetch
    for name, fields in names.items():
        module = types.ModuleType(name)
        for key, value in fields.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
    def obs(path, *, journal):
        calls['observe'] += 1
        assert Path(path).exists()
        assert Path(path).read_text().count('\n') == 121
        return tmp_path / 'observation.json', {'research_hypothesis': 'NO TRADE', 'expiry_time_utc': '2026-11-20T12:15:00+00:00'}
    def settle(*, journal, later_csv):
        calls['settle'] += 1
        return {'settled': [], 'still_pending_or_blocked': [], 'already_settled': []}
    monkeypatch.setattr(c, 'observe', obs)
    monkeypatch.setattr(c, 'settle_pending', settle)
    result = live.capture_live_once(api_key='fake-key-for-unit-test', approved=True, root=tmp_path / 'j')
    assert calls == {'renew': 0, 'fetch': 1, 'settle': 1, 'observe': 1}
    assert result['broker_orders'] == 0
    assert result['live_signal'] == 'NO TRADE'
    assert Path(result['saved_csv']).exists()


def test_prospective_scorecard_rejects_expiry_mismatch(tmp_path):
    root = tmp_path / 'j'
    observations = root / 'observations'
    settlements = root / 'settlements'
    name = 'testrecord.json'
    obs = {'recorded_at_utc': '2026-11-20T10:00:00+00:00', 'expiry_time_utc': '2026-11-20T10:15:00+00:00', 'research_hypothesis': 'UP'}
    rec = {'recorded_at_utc': '2026-11-20T10:16:00+00:00', 'expiry_time_utc': '2026-11-20T10:16:00+00:00',
           'research_hypothesis': 'UP', 'result': 'WIN', 'observation_sha256': c.digest(obs)}
    c._new_file(observations/name, c._envelope('OBSERVATION', obs))
    c._new_file(settlements/name, c._envelope('SETTLEMENT', rec))
    r = c.prospective_scorecard(root)
    assert r['counts']['WIN'] == 0 and len(r['invalid_evidence']) == 1


def test_hist_campaign_missing_dataset_fails_closed(monkeypatch):
    def raise_missing(path, payout):
        raise OSError('file missing')
    monkeypatch.setattr(c, 'historical_dataset', raise_missing)
    result = c.historical_campaign(['missing.csv'])
    assert not result['datasets']
    assert result['rejected_datasets'][0]['error'] == 'OSError'
    assert result['prediction_accuracy_verified'] is False


def test_historical_stage55_stage56_contract(monkeypatch):
    sf = types.ModuleType('scripts.run_stage55_robust_validation')
    sf.build_report = lambda p, min_nonpush, payout: {
        'source_sha256': 'ff' * 32,
        'quality': {'rows': 1440, 'first_close_utc': '2026-11-12T00:00:00+00:00', 'last_close_utc': '2026-11-12T23:59:00+00:00'},
        'stage55': {'statistical_audit': {
            'wins': 7, 'losses': 10, 'pushes': 1, 'nonpush_outcomes': 17,
            'observed_nonpush_win_rate': 7 / 17, 'wilson_95pct_nonpush_win_rate': [.2, .65],
            'one_sided_exact_pvalue_vs_break_even': 0.9243,
            'break_even_nonpush_win_rate_at_payout': 1 / 1.8, 'status': 'INSUFFICIENT_SAMPLE'},
            },
        'walk_forward': {'status': 'INSUFFICIENT_DATA'},
    }
    s56 = types.ModuleType('scripts.stage56_failure_analysis')
    s56.build_failure_report = lambda p, payout: {
        'holdout': {'wins': 7, 'losses': 10, 'pushes': 1, 'nonpush': 17, 'idealized_net_units': -4.4},
        'events': [{'entry_utc': '2026-11-12T12:00:00+00:00', 'exit_utc': '2026-11-12T12:15:00+00:00'}] * 18,
        'groups': {},
    }
    monkeypatch.setitem(sys.modules, 'scripts.run_stage55_robust_validation', sf)
    monkeypatch.setitem(sys.modules, 'scripts.stage56_failure_analysis', s56)
    r = c.historical_dataset('data.csv')
    assert r['nonpush'] == 17 and r['net_units'] == -4.4
    assert r['win_rate'] == 7 / 17
    assert r['already_inspected'] and r['status'] == 'INSUFFICIENT_SAMPLE'
    assert r['walk_forward']['status'] == 'INSUFFICIENT_DATA'


def test_historical_mismatch_fails_closed(monkeypatch):
    sf = types.ModuleType('scripts.run_stage55_robust_validation')
    sf.build_report = lambda p, min_nonpush, payout: {'stage55': {'statistical_audit': {
        'wins': 7, 'losses': 10, 'pushes': 1,
    }}}
    s56 = types.ModuleType('scripts.stage56_failure_analysis')
    s56.build_failure_report = lambda p, payout: {'holdout': {'wins': 8, 'losses': 9, 'pushes': 1}}
    monkeypatch.setitem(sys.modules, 'scripts.run_stage55_robust_validation', sf)
    monkeypatch.setitem(sys.modules, 'scripts.stage56_failure_analysis', s56)
    with pytest.raises(ValueError, match='disagreement'):
        c.historical_dataset('data.csv')
