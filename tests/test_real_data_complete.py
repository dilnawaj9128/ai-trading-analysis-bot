from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest
from dashboard.real_data_history import save_capture, load_history, resample_history, history_health
from dashboard.real_data_monitor import allow_attempt, fresh_observation_gate

NOW=datetime(2026,11,21,10,30,tzinfo=timezone.utc)
def candles(n=120):
    stamps=pd.date_range(end=pd.Timestamp(NOW)-pd.Timedelta(minutes=2),periods=n,freq='min',tz='UTC')
    return pd.DataFrame({'timestamp':stamps,'Open':[1.1]*n,'High':[1.11]*n,'Low':[1.09]*n,'Close':[1.1]*n})

def test_store_idempotent(tmp_path):
    db=tmp_path/'s.db'; df=candles()
    assert save_capture(df,db,now=NOW)['inserted']==120
    assert save_capture(df,db,now=NOW)['inserted']==0
    assert len(load_history(db))==120

def test_conflict_rolls_back(tmp_path):
    db=tmp_path/'s.db';df=candles();save_capture(df,db,now=NOW)
    changed=df.copy();changed.loc[50,'Close']=1.105
    with pytest.raises(ValueError,match='Conflicting'):
        save_capture(changed,db,now=NOW)
    assert load_history(db).Close.iloc[50]==1.1

def test_missing_intervals_rejected(tmp_path):
    df=candles();df.loc[30:,'timestamp']+=pd.Timedelta(minutes=1)
    with pytest.raises(ValueError,match='gapped'):
        save_capture(df,tmp_path/'s.db',now=NOW)

def test_stale_capture_rejected(tmp_path):
    with pytest.raises(ValueError,match='stale'):
        save_capture(candles(),tmp_path/'s.db',now=NOW+timedelta(hours=1))

def test_aggregated_complete_only():
    df=candles(n=120)
    result=resample_history(df,3)
    assert len(result)>30
    assert all((result.High>=result[['Open','Close']].max(axis=1)))
    assert len(resample_history(df,1))==120
    with pytest.raises(ValueError):resample_history(df,2)

def test_gap_health():
    df=candles(n=120).drop(index=50).reset_index(drop=True)
    assert history_health(df)['missing_minutes']==1

def test_approval_guards():
    assert not allow_attempt(active=False,consent=True,attempts=0)
    assert not allow_attempt(active=True,consent=False,attempts=0)
    assert allow_attempt(active=True,consent=True,attempts=2)
    assert not allow_attempt(active=True,consent=True,attempts=3)

def test_cadence():
    last=(NOW-timedelta(minutes=3)).isoformat()
    assert fresh_observation_gate(last,3,now=NOW)
    assert not fresh_observation_gate(last,5,now=NOW)
    with pytest.raises(ValueError):fresh_observation_gate(last,2,now=NOW)
