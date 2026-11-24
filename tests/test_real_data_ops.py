from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest
from dashboard.real_data_ops import append_event, recent_events, operational_status
from dashboard.real_data_history import save_capture

NOW=datetime(2026,11,21,10,30,tzinfo=timezone.utc)

def candles():
    times=pd.date_range(end=pd.Timestamp(NOW)-pd.Timedelta(minutes=2),periods=120,freq='min',tz='UTC')
    return pd.DataFrame({'timestamp':times,'Open':[1.1]*120,'High':[1.11]*120,'Low':[1.09]*120,'Close':[1.1]*120})


def test_ops_empty_is_not_live(tmp_path):
    result=operational_status(db_path=tmp_path/'missing.db',now=NOW)
    assert result['history_stale_over_3min']
    assert result['latest_open_utc'] is None
    assert result['provider_credit_authorized']=='NOT_CHECKED'
    assert not result['feed_mode_verified']


def test_ops_fresh_and_restart(tmp_path):
    db=tmp_path/'data.db'
    save_capture(candles(),db,now=NOW)
    one=operational_status(db_path=db,now=NOW)
    two=operational_status(db_path=db,now=NOW+timedelta(minutes=4))
    assert one['stored_candles_in_read_window']==120
    assert one['missing_minutes_in_read_window']==0
    assert not one['history_stale_over_3min']
    assert two['history_stale_over_3min']
    assert one['age_since_last_close_seconds']==60


def test_logging_is_allowlisted_and_persists(tmp_path):
    db=tmp_path/'audit.sqlite3'
    append_event('MONITOR_STARTED',db_path=db)
    append_event('FETCH_BLOCKED',db_path=db,error_class='ProviderCreditLimitReached')
    entries=recent_events(db,limit=3)
    assert len(entries)==2
    assert entries[0]['error_class']=='ProviderCreditLimitReached'
    assert entries[1]['event']=='MONITOR_STARTED'
    with pytest.raises(ValueError):
        append_event('FETCH_BLOCKED',db_path=db,error_class='SECRET=abc')
    with pytest.raises(ValueError):
        append_event('UNSAFE_EVENT',db_path=db)
    assert len(recent_events(db))==2


def test_no_network_on_module_import(tmp_path):
    assert operational_status(db_path=tmp_path/'empty.db')['broker_orders']==0
