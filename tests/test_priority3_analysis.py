"""Offline safety gates for Stage 3 attested research integration."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from scripts import run_priority3_analysis as p3

UTC = datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc)


def fake_report(**overrides):
    r = dict(analysis_only=True, execution_enabled=False, symbol='EUR/USD',
             timeframe='1min', expiry_minutes=15, candles=120,
             feed_mode='unverified', signal='NO TRADE', stale=True,
             indicators={'RSI_14': 50}, market_condition='unknown', reasons=['unverified feed'])
    r.update(overrides)
    return r


def fixture(tmp_path, monkeypatch, report=None):
    root = tmp_path / 'data'
    (root / 'api_usage').mkdir(parents=True)
    (root / 'real_market').mkdir()
    csv = root / 'real_market' / 'stage52d_new_completed.csv'
    csv.write_text('timestamp,Open,High,Low,Close\n')
    (root / 'api_usage' / 'stage52d_new_recovery_probe.json').write_text(__import__('json').dumps({
        'status': 'VERIFIED', 'checkpoint': 'VERIFIED', 'csv_path': str(csv),
        'candles': 120, 'request_id': 'a'*32, 'csv_sha256': 'b'*64,
    }))
    monkeypatch.setattr(p3, 'verified_recovery_override', lambda _: True)
    return root, lambda path, *, now: report if report is not None else fake_report()


def test_verified_report_is_research_only(tmp_path, monkeypatch):
    root, analyzer = fixture(tmp_path, monkeypatch)
    out = p3.run_priority3(root=root, now=UTC, analyzer=analyzer)
    assert out['signal'] == 'NO TRADE'
    assert out['http_requests'] == out['api_credits_used'] == 0
    assert out['source_attested'] and out['analysis_only']


def test_unverified_recovery_blocks_before_analysis(tmp_path, monkeypatch):
    root, analyzer = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(p3, 'verified_recovery_override', lambda _: False)
    with pytest.raises(ValueError, match='attestation'):
        p3.run_priority3(root=root, now=UTC, analyzer=analyzer)


@pytest.mark.parametrize('field,value', [
    ('signal', 'UP'), ('signal', 'DOWN'), ('feed_mode', 'verified'),
    ('analysis_only', False), ('execution_enabled', True),
    ('candles', 119), ('expiry_minutes', 5), ('symbol', 'GBP/USD'),
])
def test_unsafe_or_mismatched_report_rejected(tmp_path, monkeypatch, field, value):
    root, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        p3.run_priority3(root=root, now=UTC,
                         analyzer=lambda p, *, now: fake_report(**{field: value}))


def test_recovery_csv_path_mismatch_blocks(tmp_path, monkeypatch):
    root, analyzer = fixture(tmp_path, monkeypatch)
    journal = root / 'api_usage' / 'stage52d_new_recovery_probe.json'
    import json
    evidence = json.loads(journal.read_text())
    evidence['csv_path'] = '/tmp/wrong.csv'
    journal.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='path mismatch'):
        p3.run_priority3(root=root, now=UTC, analyzer=analyzer)
