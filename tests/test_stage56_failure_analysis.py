from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from scripts.stage56_failure_analysis import analyze_trades


def frame(n=150):
    start=datetime(2026,11,16,tzinfo=timezone.utc)
    times=[start+timedelta(minutes=i) for i in range(n)]
    close=[1.1+i*.00001 for i in range(n)]
    return pd.DataFrame({'timestamp':times,'Close':close,'High':[v+.0001 for v in close],'Low':[v-.0001 for v in close]})


def trade(entry=45,result='LOSS',direction='UP',partition='holdout'):
    start=datetime(2026,11,16,tzinfo=timezone.utc)
    return {'partition':partition,'signal':direction,'result':result,
            'entry_time_utc':(start+timedelta(minutes=entry)).isoformat(),
            'exit_time_utc':(start+timedelta(minutes=entry+15)).isoformat()}


def test_counts_and_groups():
    r=analyze_trades([trade(45,'WIN'),trade(70,'LOSS','DOWN'),trade(90,'PUSH')],frame(),min_group=2)
    assert r['holdout']=={'wins':1,'losses':1,'pushes':1,'nonpush':2,'idealized_net_units':-.2}
    assert r['groups']['direction']['UP']['pushes']==1
    assert r['live_signal']=='NO TRADE'
    assert r['http_requests']==0


def test_ignores_training_trades():
    r=analyze_trades([trade(45,'WIN',partition='training')],frame())
    assert r['holdout']['nonpush']==0


def test_rejects_overlap():
    with pytest.raises(ValueError,match='Overlapping'):
        analyze_trades([trade(45),trade(48)],frame())


def test_rejects_bad_expiry():
    t=trade(45)
    t['exit_time_utc']=(datetime(2026,11,16,tzinfo=timezone.utc)+timedelta(minutes=46)).isoformat()
    with pytest.raises(ValueError,match='15-minute'):
        analyze_trades([t],frame())


def test_no_future_candle_leakage():
    a=frame()
    r1=analyze_trades([trade(45)],a)
    b=a.copy()
    b.loc[45:,'Close']=b.loc[45:,'Close']+0.5
    b.loc[45:,'High']=b.loc[45:,'High']+0.5
    b.loc[45:,'Low']=b.loc[45:,'Low']+0.5
    r2=analyze_trades([trade(45)],b)
    assert r1['events'][0]['prior_trend']==r2['events'][0]['prior_trend']
    assert r1['events'][0]['prior_volatility']==r2['events'][0]['prior_volatility']


def test_rejects_unknown_result():
    with pytest.raises(ValueError,match='Unexpected'):
        analyze_trades([trade(45,'OPEN')],frame())


def test_rejects_nonchronological_candles():
    f=frame()
    f.loc[45,'timestamp']=f.loc[44,'timestamp']
    with pytest.raises(ValueError,match='chronological'):
        analyze_trades([],f)


def test_rejects_bad_payout():
    with pytest.raises(ValueError,match='payout'):
        analyze_trades([],frame(),payout=0)


def test_low_sample_groups_not_promoted():
    r=analyze_trades([trade(45,'WIN')],frame())
    assert r['groups']['direction']['UP']['interpretation']=='TOO_FEW_OBSERVATIONS'
    assert r['status']=='INSUFFICIENT_HOLDOUT'


def test_invalid_time_rejected():
    t=trade(45)
    t['entry_time_utc']='2026-11-16 00:45:00'
    with pytest.raises(ValueError,match='Naive'):
        analyze_trades([t],frame())
