import sys
import types
from dashboard.credit_repair_control import credit_repair_preview, reconcile_receipts_safely


def test_block_on_insufficient_headroom(monkeypatch):
    from dashboard import twelve_data_readiness
    monkeypatch.setattr(twelve_data_readiness, 'readiness', lambda: dict(
        provider_credits_left=7, outstanding_reserved=6, conservative_headroom=1,
        minimum_one_fetch_headroom=2, status='STALE_SNAPSHOT', reason='stale'))
    value=credit_repair_preview()
    assert value['fetch_headroom_blocked']
    assert 'pending reservations 6' in value['message']
    assert value['provider_requests']==0


def test_stale_but_sufficient_not_authorization(monkeypatch):
    from dashboard import twelve_data_readiness
    monkeypatch.setattr(twelve_data_readiness, 'readiness', lambda: dict(
        provider_credits_left=7, outstanding_reserved=2, conservative_headroom=5,
        minimum_one_fetch_headroom=2, status='STALE_SNAPSHOT', reason='stale'))
    value=credit_repair_preview()
    assert not value['fetch_headroom_blocked']
    assert value['provider_status']=='STALE_SNAPSHOT'


def test_verified_only_reconciler_called(monkeypatch):
    from market_data import verified_reservation_settlement as m
    monkeypatch.setattr(m,'reconcile_verified_historical',lambda: {
        'status':'RECONCILED', 'outstanding_reserved':5, 'settled_request_prefixes':['abc']})
    result=reconcile_receipts_safely()
    assert result['ok'] and result['settled_count']==1
    assert result['provider_requests']==0


def test_unverified_no_auto_settle(monkeypatch):
    from market_data import verified_reservation_settlement as m
    def blocked(): raise m.VerifiedSettlementBlocked('no receipts')
    monkeypatch.setattr(m,'reconcile_verified_historical',blocked)
    result=reconcile_receipts_safely()
    assert not result['ok']
