"""Regression for strict receipt-based settlement. No real HTTP or broker calls."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from market_data.authorization_journal import create_intent, finalize_intent, journal_path_for
from market_data.verified_reservation_settlement import (
    VerifiedSettlementBlocked, reconcile_verified_historical,
    settle_verified_normal, valid_recovery_settlement_receipt,
)
from market_data.unified_request_guard import _load_ledger
from market_data.recovery_verified_gate import verified_recovery_override
from market_data.recovery_transport import recover_once
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_stage52d_recovery_transport import setup as recovery_setup, FakeSession, MockResponse


def make_ledger(tmp_path, *, status='PENDING', legacy=0):
    root = tmp_path / 'api_usage'
    root.mkdir()
    provider = root / 'provider_credits.json'
    provider.write_text(json.dumps({'version': 1, 'observed_at': '2026-11-20T06:00:00+00:00',
                                    'credits_used': 1, 'credits_left': 6}))
    rid = 'a' * 32
    tx = journal_path_for(provider)
    create_intent(tx, request_id=rid, authorized_at='2026-11-20T06:00:00+00:00', credits=1)
    finalize_intent(tx, rid)
    ledger_file = root / 'provider_credits.json.reservations.json'
    ledger_file.write_text(json.dumps({'version': 2, 'reserved': legacy + 1,
                                       'legacy_reserved': legacy, 'requests': {
                                           rid: {'credits': 1, 'status': status,
                                                 'authorized_at': '2026-11-20T06:00:00+00:00',
                                                 'snapshot_observed_at': '2026-11-20T06:00:00+00:00'},
                                       }}))
    return provider, rid


def test_future_verified_normal_settles_exact_request_and_preserves_legacy(tmp_path):
    provider, rid = make_ledger(tmp_path, legacy=2)
    assert settle_verified_normal(provider_path=provider, request_id=rid, credits_left=5, candles=120)
    state = _load_ledger(provider.with_name(provider.name + '.reservations.json'))
    assert state['reserved'] == 2
    assert state['legacy_reserved'] == 2
    assert state['requests'][rid]['status'] == 'SETTLED'
    receipt = provider.parent / 'verified_settlement_receipts' / (rid + '.json')
    assert receipt.exists()
    assert not any('api' in k.lower() for k in json.loads(receipt.read_text()))


def test_uncertain_is_not_released(tmp_path):
    provider, rid = make_ledger(tmp_path, status='UNCERTAIN')
    with pytest.raises(VerifiedSettlementBlocked):
        settle_verified_normal(provider_path=provider, request_id=rid, credits_left=6, candles=120)
    assert _load_ledger(provider.with_name(provider.name+'.reservations.json'))['reserved'] == 1


def test_missing_response_metadata_fails_closed(tmp_path):
    provider, rid = make_ledger(tmp_path)
    for balance, count in ((None,120),(3,0),(-1,120)):
        with pytest.raises(VerifiedSettlementBlocked):
            settle_verified_normal(provider_path=provider, request_id=rid,
                                   credits_left=balance, candles=count)
    assert _load_ledger(provider.with_name(provider.name+'.reservations.json'))['reserved'] == 1


def test_unknown_request_id_does_not_settle(tmp_path):
    provider, rid = make_ledger(tmp_path)
    with pytest.raises(VerifiedSettlementBlocked):
        settle_verified_normal(provider_path=provider, request_id='b'*32, credits_left=6, candles=100)
    assert _load_ledger(provider.with_name(provider.name+'.reservations.json'))['reserved'] == 1


def test_no_historical_receipt_means_no_automatic_settlement(tmp_path):
    provider, rid = make_ledger(tmp_path)
    report = reconcile_verified_historical(provider_path=provider)
    assert report['settled_request_prefixes'] == []
    assert report['outstanding_reserved'] == 1
    assert report['http_requests'] == 0


def test_historical_verified_renewal_idempotent(tmp_path):
    provider, rid = make_ledger(tmp_path)
    record = {'request_id': rid, 'status': 'VERIFIED', 'http_attempted': True,
              'credits_left': 5, 'candles': 120,
              'verified_at_utc': '2026-11-20T06:00:01+00:00'}
    (provider.parent / 'verified_credit_renewals.json').write_text(json.dumps({'version': 1, 'attempts': [record]}))
    first = reconcile_verified_historical(provider_path=provider)
    assert first['outstanding_reserved'] == 0
    assert first['settled_request_prefixes'] == [rid[:10]]
    second = reconcile_verified_historical(provider_path=provider)
    assert second['outstanding_reserved'] == 0
    assert second['already_settled_prefixes'] == [rid[:10]]


def test_unverified_renewal_does_not_settle(tmp_path):
    provider, rid = make_ledger(tmp_path)
    (provider.parent/'verified_credit_renewals.json').write_text(json.dumps({'version':1,'attempts':[{
        'request_id':rid,'status':'UNCERTAIN','http_attempted':True,
    }]}))
    report = reconcile_verified_historical(provider_path=provider)
    assert report['outstanding_reserved'] == 1


def test_recovery_settlement_keeps_gate_and_original_uncertain(recovery_setup, monkeypatch):
    root, args = recovery_setup
    # Reproduce the production attestation paths exactly.
    base = root.parent
    reports = base / 'recovery_reports'
    reports.mkdir()
    case = reports / 'stage52d_20261119_uncertain_case.json'
    archive = reports / 'stage52d_historical_provider_credits.json'
    case.write_bytes(args['case_path'].read_bytes())
    archive.write_bytes(args['archive_path'].read_bytes())
    args['case_path'], args['archive_path'] = case, archive
    args['claim_path'] = root / 'recovery_txn_claim.json'
    args['recovery_journal_path'] = root / 'stage52d_new_recovery_probe.json'
    args['csv_path'] = base / 'real_market' / 'stage52d_new_completed.csv'
    # root originally named 'api', but preflight relies on filenames, not name
    monkeypatch.chdir(base)
    old_bytes = args['old_probe_path'].read_bytes()
    recover_once(approved=True, session=FakeSession(response=MockResponse()), **args)
    assert verified_recovery_override(args['old_probe_path']) is True
    report = reconcile_verified_historical(provider_path=args['provider_path'])
    assert report['outstanding_reserved'] == 0
    assert verified_recovery_override(args['old_probe_path']) is True
    assert args['old_probe_path'].read_bytes() == old_bytes
    assert reconcile_verified_historical(provider_path=args['provider_path'])['outstanding_reserved'] == 0


def test_missing_receipt_after_settlement_invalidates_recovery_gate(recovery_setup, monkeypatch):
    root, args = recovery_setup
    reports = root.parent / 'recovery_reports'
    reports.mkdir()
    case = reports / 'stage52d_20261119_uncertain_case.json'
    archive = reports / 'stage52d_historical_provider_credits.json'
    case.write_bytes(args['case_path'].read_bytes())
    archive.write_bytes(args['archive_path'].read_bytes())
    args.update(case_path=case, archive_path=archive,
                claim_path=root/'recovery_txn_claim.json',
                recovery_journal_path=root/'stage52d_new_recovery_probe.json',
                csv_path=root.parent/'real_market'/'stage52d_new_completed.csv')
    monkeypatch.chdir(root.parent)
    recover_once(approved=True, session=FakeSession(response=MockResponse()), **args)
    rid = _load_ledger(root/'provider_credits.json.reservations.json')['requests'].popitem()[0]
    reconcile_verified_historical(provider_path=args['provider_path'])
    receipt = root / 'verified_settlement_receipts' / (rid + '.json')
    receipt.unlink()
    assert verified_recovery_override(args['old_probe_path']) is False
