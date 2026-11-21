from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest
from dashboard.real_data_mode import validate_ohlc, analyze_frame, fetch_real_data_once

NOW = datetime(2026,11,21,10,30,tzinfo=timezone.utc)

def candles(n=120):
    stamps=pd.date_range(end=pd.Timestamp(NOW)-pd.Timedelta(minutes=2),periods=n,freq='min',tz='UTC')
    return pd.DataFrame({'timestamp':stamps,'Open':[1.10]*n,'High':[1.11]*n,'Low':[1.09]*n,'Close':[1.10]*n})

def indicators(df):
    result=df.copy()
    result['EMA_20']=1.101
    result['RSI_14']=52.0
    return result

def test_valid_candles_and_indicators():
    x=analyze_frame(candles(),now=NOW,indicator_fn=indicators)
    assert x['quality']['quality']=='PASS'
    assert x['indicators']['RSI_14']==52
    assert x['signal_generation'] is False

@pytest.mark.parametrize('bad', ['duplicate','unfinished','bad_high','gap'])
def test_bad_candles(bad):
    df=candles()
    if bad=='duplicate': df.loc[20,'timestamp']=df.loc[19,'timestamp']
    elif bad=='unfinished': df.loc[len(df)-1,'timestamp']=NOW
    elif bad=='bad_high': df.loc[10,'High']=1.0
    else: df.loc[30:,'timestamp']+=pd.Timedelta(minutes=1)
    if bad=='gap':
        assert validate_ohlc(df,now=NOW)[1]['quality']=='GAPS_DETECTED'
    else:
        with pytest.raises(ValueError): validate_ohlc(df,now=NOW)

def test_no_approval_no_fetch():
    with pytest.raises(ValueError): fetch_real_data_once(approved=False,api_key='secret')

def test_single_guarded_fetch_without_renewal():
    count={'fetch':0}
    def fetch(cfg,*,api_key):
        count['fetch']+=1
        return {'analysis_only':True,'execution_enabled':False,
                'symbol':'EUR/USD','interval':'1min','candles':120,'frame':candles()}
    result=fetch_real_data_once(approved=True,api_key='test',credit_loader=lambda:object(),
              renewal=lambda **kw:pytest.fail('not needed'),fetcher=fetch,now=NOW,indicator_fn=indicators)
    assert count['fetch']==1 and not result['renewal_used']

def test_renewal_before_fetch():
    calls=[]
    def renew(**kwargs):calls.append('renew')
    def fetch(cfg,*,api_key):
        calls.append('fetch')
        return {'analysis_only':True,'execution_enabled':False,
                'symbol':'EUR/USD','interval':'1min','candles':120,'frame':candles()}
    r=fetch_real_data_once(approved=True,api_key='test',credit_loader=lambda:None,
                renewal=renew,fetcher=fetch,now=NOW,indicator_fn=indicators)
    assert calls==['renew','fetch'] and r['renewal_used']

def test_invalid_provider_response_no_signal():
    def fetch(cfg,*,api_key):return {'analysis_only':True,'execution_enabled':True,
               'symbol':'EUR/USD','interval':'1min','candles':120,'frame':candles()}
    with pytest.raises(ValueError):
        fetch_real_data_once(approved=True,api_key='test',credit_loader=lambda:object(),
                            fetcher=fetch,now=NOW,indicator_fn=indicators)
