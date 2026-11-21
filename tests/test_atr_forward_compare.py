import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from scripts import run_atr_forward_compare as ab


def frame(start, length=120):
    times = pd.date_range(start=start, periods=length, freq='min', tz='UTC')
    vals = [1.10 + 0.00001 * i for i in range(length)]
    return pd.DataFrame({'timestamp': times, 'Open': vals, 'High': [x+0.00002 for x in vals],
                         'Low': [x-0.00002 for x in vals], 'Close': vals})


def fake_candles(monkeypatch, f):
    monkeypatch.setattr(ab, '_candles', lambda p: (p, f, {}))
    # record imports _candles lazily from research module
    import research.real_prediction_campaign as c
    monkeypatch.setattr(c, '_candles', lambda p: (p, f, {}))


def test_record_is_prospective_and_immutable(tmp_path, monkeypatch):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    f = frame(start)
    fake_candles(monkeypatch, f)
    monkeypatch.setattr(ab, 'signals', lambda df: {'control_025':'UP', 'challenger_050':'NO TRADE'})
    source = tmp_path/'capture.csv'; source.write_text('fixture')
    journal=tmp_path/'journal'
    with pytest.raises(ValueError, match='freshly'):
        ab.record(source, journal=journal, now=start+timedelta(minutes=124))
    target, obs = ab.record(source, journal=journal, now=start+timedelta(minutes=120,seconds=10))
    assert obs['models']['control_025']=='UP'
    assert obs['live_signal']=='NO TRADE'
    with pytest.raises(ValueError, match='non-overlap'):
        ab.record(source, journal=journal, now=start+timedelta(minutes=120,seconds=11))
    assert target.exists()


def test_paired_settlement_requires_exact_candle_and_entry(tmp_path, monkeypatch):
    start=datetime(2026,11,20,10,tzinfo=timezone.utc)
    source=tmp_path/'capture.csv'; source.write_text('fixture')
    journal=tmp_path/'journal'
    fake_candles(monkeypatch, frame(start))
    monkeypatch.setattr(ab,'signals',lambda df:{'control_025':'UP','challenger_050':'NO TRADE'})
    ab.record(source,journal=journal,now=start+timedelta(minutes=120,seconds=10))
    assert ab.settle(source,journal=journal,now=start+timedelta(minutes=120,seconds=10))==[]
    fake_candles(monkeypatch,frame(start,136))
    done=ab.settle(source,journal=journal,now=start+timedelta(minutes=136))
    assert done[0]['results']=={'control_025':'WIN','challenger_050':'ABSTAINED'}
    assert ab.settle(source,journal=journal,now=start+timedelta(minutes=136))==[]
    summary=ab.report(journal=journal)
    assert summary['arms']['control_025']['resolved_directional']==1
    assert summary['arms']['challenger_050']['resolved_directional']==0


def test_stale_capture_cannot_fake_prospective(tmp_path,monkeypatch):
    start=datetime(2026,11,20,10,tzinfo=timezone.utc)
    fake_candles(monkeypatch,frame(start))
    source=tmp_path/'cap.csv';source.write_text('test')
    with pytest.raises(ValueError,match='freshly'):
        ab.record(source,journal=tmp_path/'j',now=start+timedelta(hours=2,minutes=40))
    assert ab.report(journal=tmp_path/'j')['pairs_recorded']==0


def test_pair_checksum_tampering_fails(tmp_path,monkeypatch):
    start=datetime(2026,11,20,10,tzinfo=timezone.utc)
    fake_candles(monkeypatch,frame(start))
    source=tmp_path/'cap.csv';source.write_text('test')
    monkeypatch.setattr(ab,'signals',lambda df:{'control_025':'UP','challenger_050':'DOWN'})
    target,_=ab.record(source,journal=tmp_path/'j',now=start+timedelta(minutes=120,seconds=10))
    obj=json.loads(target.read_text());obj['record']['models']['control_025']='DOWN'
    target.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='checksum'):
        ab.report(journal=tmp_path/'j')
