"""Offline regression for provider completed-candle lag vs wall-clock guard."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types

from research.real_prediction_campaign import _new_file, _envelope


def test_lag_buffer_blocks_before_provider_http(tmp_path, monkeypatch):
    from scripts.run_real_prediction_live_once import capture_live_once
    now = datetime.now(timezone.utc)
    prior = {
        'decision_time_utc': (now-timedelta(minutes=16)).isoformat(),
        'recorded_at_utc': (now-timedelta(minutes=15, seconds=30)).isoformat(),
        'expiry_time_utc': (now-timedelta(minutes=1)).isoformat(),
    }
    _new_file(tmp_path/'observations'/'prior.json', _envelope('OBSERVATION',prior))
    names = {
        'market_data.verified_reservation_settlement': 'reconcile_verified_historical',
        'market_data.provider_credit_state': 'load_credit_state',
        'market_data.verified_credit_renewal': 'renew_verified_credits_once',
        'market_data.authorized_live_fetch': 'fetch_authorized_live_candles',
        'config.market_config': 'create_research_config',
    }
    for name, method in names.items():
        m=types.ModuleType(name)
        setattr(m,method,lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Unexpected external code call')))
        monkeypatch.setitem(sys.modules,name,m)
    result = capture_live_once(api_key='unit-test-not-real',approved=True,root=tmp_path)
    assert result['status']=='BLOCKED_NO_HTTP'
    assert result['provider_requests']==0
    assert result['reason']=='PROVIDER_CANDLE_LAG_BUFFER'
