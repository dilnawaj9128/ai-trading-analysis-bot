from pathlib import Path

from scripts import run_atr_campaign_once as cli


def fake_campaign(status="NOT_REQUESTED", saved=None):
    result={"live":{"status":status}, "forward_accuracy":{
        "pending_observations": ["pending"], "resolved_directional":0,
        "counts":{"WIN":0,"LOSS":0,"PUSH":0,"ABSTAINED":1}}}
    if saved is not None: result["live"]["saved_csv"]=str(saved)
    return result


def fake_stats():
    return {"pairs_recorded":0,"pairs_settled":0,"arms":{
        "control_025":{"resolved_directional":0,"win_rate":None},
        "challenger_050":{"resolved_directional":0,"win_rate":None}},
        "break_even":1/1.8,"comparison_status":"INSUFFICIENT_INDEPENDENT_EVIDENCE"}


def test_offline_only_uses_existing_captures(tmp_path,monkeypatch):
    folder=tmp_path/"captures";folder.mkdir()
    (folder/"old.csv").write_text("old")
    monkeypatch.setattr(cli.ab,"settle",lambda *a,**kw:[])
    monkeypatch.setattr(cli.ab,"report",lambda **kw:fake_stats())
    def existing(*,approved,api_key):
        assert not approved and api_key is None
        return fake_campaign()
    monkeypatch.setattr(cli,"run_existing",existing)
    result=cli.run(capture_dir=folder,journal=tmp_path/"journal",output=tmp_path/"report.json")
    assert result["new_saved_captures"]==0
    assert result["new_pair"] is None


def test_successful_bounded_fetch_records_pair_once(tmp_path,monkeypatch):
    folder=tmp_path/"captures";folder.mkdir()
    new=folder/"new.csv"
    monkeypatch.setattr(cli.ab,"settle",lambda *a,**kw:[])
    monkeypatch.setattr(cli.ab,"report",lambda **kw:fake_stats())
    def existing(*,approved,api_key):
        assert approved
        new.write_text("fixture")
        return fake_campaign("FETCHED_OR_RECORDED",new)
    monkeypatch.setattr(cli,"run_existing",existing)
    monkeypatch.setattr(cli.ab,"record",lambda p,**kw:(tmp_path/"obs.json",{
        "models":{"control_025":"UP","challenger_050":"NO TRADE"},
        "decision_utc":"2026-11-21T10:00:00+00:00",
        "expiry_utc":"2026-11-21T10:15:00+00:00"
    }))
    result=cli.run(approved=True,capture_dir=folder,journal=tmp_path/"j",output=tmp_path/"r.json")
    assert result["pair_recording_status"]=="RECORDED"
    assert result["new_saved_captures"]==1


def test_blocked_status_does_not_record(tmp_path,monkeypatch):
    folder=tmp_path/"captures";folder.mkdir()
    monkeypatch.setattr(cli.ab,"settle",lambda *a,**kw:[])
    monkeypatch.setattr(cli.ab,"report",lambda **kw:fake_stats())
    monkeypatch.setattr(cli,"run_existing",lambda **kw:fake_campaign("BLOCKED_NO_HTTP"))
    def forbidden(*a,**kw):raise AssertionError("Should not record")
    monkeypatch.setattr(cli.ab,"record",forbidden)
    result=cli.run(approved=True,capture_dir=folder,journal=tmp_path/"j",output=tmp_path/"r.json")
    assert result["pair_recording_status"]=="FETCH_BLOCKED_NO_PAIRED_PREDICTION"


def test_stale_new_capture_not_forged(tmp_path,monkeypatch):
    folder=tmp_path/"captures";folder.mkdir()
    new=folder/"new.csv"
    monkeypatch.setattr(cli.ab,"settle",lambda *a,**kw:[])
    monkeypatch.setattr(cli.ab,"report",lambda **kw:fake_stats())
    def existing(**kw):
        new.write_text("fixture")
        return fake_campaign("FETCHED_OR_RECORDED",new)
    monkeypatch.setattr(cli,"run_existing",existing)
    def stale(*a,**kw): raise ValueError("stale")
    monkeypatch.setattr(cli.ab,"record",stale)
    result=cli.run(approved=True,capture_dir=folder,journal=tmp_path/"j",output=tmp_path/"r.json")
    assert result["pair_recording_status"]=="SKIPPED_VALUEERROR"
