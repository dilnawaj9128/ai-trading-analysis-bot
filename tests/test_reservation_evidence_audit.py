import json
from pathlib import Path
import pytest
from scripts.run_reservation_evidence_audit import audit


def seed(tmp, status='PENDING'):
    provider=tmp/'provider_credits.json'
    provider.write_text('{"version":1,"observed_at":"2026-11-20T00:00:00+00:00","credits_left":7,"credits_used":1}')
    rid='a'*32
    (tmp/'provider_credits.json.reservations.json').write_text(json.dumps({'version':2,'reserved':1,'legacy_reserved':0,'requests':{rid:{'credits':1,'status':status}}}))
    (tmp/'provider_credits.json.authorization_journal.json').write_text(json.dumps({'version':1,'transactions':{rid:{'status':'FINALIZED','credits':1,'authorized_at':'2026-11-20T00:00:00+00:00'}}}))
    return provider, rid


def test_pending_without_receipt_stays_unreconciled(tmp_path):
    provider, rid=seed(tmp_path)
    before=(tmp_path/'provider_credits.json.reservations.json').read_bytes()
    result=audit(provider)
    assert result['requests'][0]['classification']=='NO_BOUND_SUCCESS_RECEIPT_DO_NOT_RELEASE'
    assert not result['safe_to_auto_release']
    assert (tmp_path/'provider_credits.json.reservations.json').read_bytes()==before


def test_uncertain_never_released_even_if_verified_marker(tmp_path):
    provider,rid=seed(tmp_path,'UNCERTAIN')
    (tmp_path/'stage52d_new_recovery_probe.json').write_text(json.dumps({'status':'VERIFIED','checkpoint':'VERIFIED','request_id':rid}))
    assert audit(provider)['requests'][0]['classification']=='UNRESOLVED_DO_NOT_RELEASE'


def test_verified_receipt_only_flags_review(tmp_path):
    provider,rid=seed(tmp_path)
    (tmp_path/'verified_credit_renewals.json').write_text(json.dumps({'attempts':[{'status':'VERIFIED','request_id':rid}]}))
    assert audit(provider)['requests'][0]['classification']=='REVIEW_VERIFIED_RECEIPT_NOT_AUTO_SETTLED'
    assert audit(provider)['outstanding_reserved']==1


def test_journal_mismatch_fails_closed(tmp_path):
    provider,rid=seed(tmp_path)
    (tmp_path/'provider_credits.json.authorization_journal.json').write_text('{"version":1,"transactions":{}}')
    with pytest.raises(ValueError,match='disagree'):
        audit(provider)
