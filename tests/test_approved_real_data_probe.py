from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from scripts import approved_real_data_probe as module

NOW = datetime(2026, 11, 19, 12, 30, tzinfo=timezone.utc)

def test_requires_explicit_approval(tmp_path):
    with pytest.raises(module.ProbeBlocked, match='Explicit approval'):
        module.probe_once(approved=False, state_path=tmp_path/'probe.json')

def test_network_failure_is_single_use(tmp_path, monkeypatch):
    monkeypatch.setattr(module.td, 'reserve_request', lambda **kw: None)
    class Broken:
        calls = 0
        def get(self, *a, **k):
            self.calls += 1
            raise TimeoutError('offline timeout')
    session = Broken()
    kwargs = dict(approved=True, api_key='fake-key', state_path=tmp_path/'probe.json',
                  budget_path=tmp_path/'budget.json', provider_path=tmp_path/'credits.json',
                  csv_path=tmp_path/'candles.csv', now=NOW, session=session)
    with pytest.raises(TimeoutError): module.probe_once(**kwargs)
    with pytest.raises(module.ProbeBlocked, match='unresolved'): module.probe_once(**kwargs)
    assert session.calls == 1

def test_verified_path_and_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr(module.td, 'reserve_request', lambda **kw: None)
    class FakeFrame:
        def to_csv(self, path, index=False):
            from pathlib import Path
            Path(path).write_text('timestamp,Open,High,Low,Close\n2026-11-19,1,2,1,2\n')
    monkeypatch.setattr(module.td, 'parse_candles', lambda *a, **k:
        {'frame':FakeFrame(), 'candles':1, 'latest_utc': NOW.isoformat(), 'stale':False})
    monkeypatch.setattr(module, 'refresh_credits_from_response', lambda *a, **k:
        SimpleNamespace(updated=True, credits_left=7))
    class FakeResponse:
        status_code=200
        def raise_for_status(self):pass
        def json(self): return {'meta': {'symbol':'EUR/USD','interval':'1min'}, 'values':[1]}
    class Session:
        calls=0
        def get(self,*a,**k): self.calls+=1; return FakeResponse()
    session=Session()
    kwargs=dict(approved=True, api_key='fake-key', state_path=tmp_path/'probe.json',
        budget_path=tmp_path/'budget.json', provider_path=tmp_path/'credits.json',
        csv_path=tmp_path/'candles.csv', now=NOW, session=session)
    result=module.probe_once(**kwargs)
    assert result['status']=='VERIFIED'
    assert (tmp_path/'candles.csv').exists()
    with pytest.raises(module.ProbeBlocked, match='cooldown'):
        module.probe_once(**kwargs)
    assert session.calls == 1
