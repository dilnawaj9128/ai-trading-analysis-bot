from pathlib import Path
from scripts.run_accuracy_all import archive_settlement_pass, accuracy_report, run


def test_empty_archive_does_not_use_http(tmp_path):
    report = archive_settlement_pass(tmp_path)
    assert report['captures_found'] == 0
    assert report['new_settlements'] == []


def test_no_approval_never_calls_live(tmp_path, monkeypatch):
    import scripts.run_real_prediction_live_once as live
    def forbidden(**kwargs):
        raise AssertionError('Live fetch must not run')
    monkeypatch.setattr(live, 'capture_live_once', forbidden)
    out = run(journal=str(tmp_path/'journal'), report_dir=str(tmp_path/'report'))
    assert out['live']['status'] == 'NOT_REQUESTED'
    assert out['forward_accuracy']['resolved_directional'] == 0
    assert Path(out['report_path']).is_file()


def test_approval_without_key_no_http(tmp_path):
    out = run(journal=str(tmp_path/'journal'), report_dir=str(tmp_path/'report'), approved=True, api_key=None)
    assert out['live']['status'] == 'BLOCKED_NO_KEY'


def test_score_has_no_unsupported_win_rate(tmp_path):
    report, _ = accuracy_report(tmp_path/'journal', tmp_path/'report')
    assert report['win_rate'] is None
    assert report['hypothetical_net_units'] == 0
    assert report['prediction_accuracy_verified'] is False


def test_bad_payout_fails_closed(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        accuracy_report(tmp_path/'journal', tmp_path/'report', payout=0)
