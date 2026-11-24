import json
from datetime import datetime, timezone, timedelta
from dashboard.twelve_data_readiness import readiness

NOW = datetime(2026,11,21,10,0,tzinfo=timezone.utc)


def setup(tmp_path, left=7, reserved=5, age=0):
    p=tmp_path/'provider_credits.json'
    p.write_text(json.dumps({'version':1,'observed_at':(NOW-timedelta(seconds=age)).isoformat(),
                             'credits_left':left,'credits_used':1}))
    entries={f'id_{i}':{'status':'PENDING','credits':1,
              'authorized_at':(NOW).isoformat()} for i in range(reserved)}
    (tmp_path/'provider_credits.json.reservations.json').write_text(json.dumps({
       'version':2,'reserved':reserved,'legacy_reserved':0,'requests':entries
    }))
    return p


def test_preflight_possible_but_not_authorization(tmp_path):
    result=readiness(provider_path=setup(tmp_path,7,5),now=NOW)
    assert result['status']=='PREFLIGHT_POSSIBLE'
    assert result['conservative_headroom']==2
    assert result['authorization_granted'] is False


def test_blocks_when_reserved_exhausts_headroom(tmp_path):
    result=readiness(provider_path=setup(tmp_path,7,6),now=NOW)
    assert result['status']=='BLOCKED_LOCAL_HEADROOM'
    assert result['conservative_headroom']==1


def test_stale_snapshot_is_not_readiness(tmp_path):
    result=readiness(provider_path=setup(tmp_path,7,5,age=301),now=NOW)
    assert result['status']=='STALE_SNAPSHOT'


def test_missing_ledger_fails_closed(tmp_path):
    p=setup(tmp_path)
    (tmp_path/'provider_credits.json.reservations.json').unlink()
    result=readiness(provider_path=p,now=NOW)
    assert result['status']=='UNKNOWN'


def test_bad_ledger_fails_closed(tmp_path):
    p=setup(tmp_path)
    (tmp_path/'provider_credits.json.reservations.json').write_text('corrupted')
    result=readiness(provider_path=p,now=NOW)
    assert result['status']=='UNKNOWN'


def test_future_snapshot_fails_closed(tmp_path):
    p=setup(tmp_path, age=-1)
    result=readiness(provider_path=p,now=NOW)
    assert result['status']=='UNKNOWN'


def test_readiness_is_read_only(tmp_path):
    p=setup(tmp_path)
    ledger=tmp_path/'provider_credits.json.reservations.json'
    first=(p.read_bytes(),ledger.read_bytes())
    readiness(provider_path=p, now=NOW)
    assert (p.read_bytes(),ledger.read_bytes())==first
