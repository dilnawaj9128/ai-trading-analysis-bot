import json

from backend.stage48_api import (
    api_response,
    build_snapshot,
    read_latest_report,
    valid_metrics,
)


HASH = "a" * 64


def metrics():
    return {
        "folds": 4,
        "total_trades": 20,
        "wins": 8,
        "losses": 11,
        "pushes": 1,
        "resolved": 19,
        "win_rate_percent": 42.1053,
        "break_even_win_rate_percent": 55.5556,
        "net_units": -4.6,
        "max_drawdown_units": 4.6,
    }


def reports(tmp_path):
    s46 = tmp_path / "stage46"
    s47 = tmp_path / "stage47"
    s46.mkdir()
    s47.mkdir()

    report46 = {
        "stage": 46,
        "dataset_sha256": HASH,
        "audit_type": "STAGE36_WALK_FORWARD",
        "status": "OFFLINE_RECONCILED",
        "errors": [],
        "metrics": metrics(),
        "analysis_only": True,
        "execution_enabled": False,
        "api_requests_executed": 0,
        "dataset_origin_verified": False,
        "forward_accuracy_proven": False,
    }

    report47 = {
        "stage": 47,
        "dataset_sha256": HASH,
        "status": "CHECKPOINTS_PASSED",
        "signal_checks": 108,
        "signal_failures": 0,
        "selection_checks": 4,
        "selection_failures": 0,
        "analysis_only": True,
        "execution_enabled": False,
        "api_requests_executed": 0,
        "dataset_origin_verified": False,
        "forward_accuracy_proven": False,
    }

    write(s46 / "report.json", report46)
    write(s47 / "report.json", report47)

    return s46, s47, report46, report47


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_valid_offline_reports(tmp_path):
    s46, s47, _, _ = reports(tmp_path)

    snapshot = build_snapshot(s46, s47)

    assert snapshot["research_status"] == "OFFLINE_AUDITS_AVAILABLE"
    assert snapshot["historical_metrics"]["total_trades"] == 20


def test_missing_reports_fail_closed(tmp_path):
    snapshot = build_snapshot(
        tmp_path / "missing46",
        tmp_path / "missing47",
    )

    assert snapshot["research_status"] == "RESEARCH_EVIDENCE_INCOMPLETE"
    assert snapshot["historical_metrics"] is None


def test_dataset_hash_mismatch_blocks(tmp_path):
    s46, s47, _, report47 = reports(tmp_path)
    report47["dataset_sha256"] = "b" * 64
    write(s47 / "report.json", report47)

    snapshot = build_snapshot(s46, s47)

    assert snapshot["reports"]["same_dataset"] is False
    assert snapshot["historical_metrics"] is None


def test_corrupt_report_blocks(tmp_path):
    s46, s47, _, _ = reports(tmp_path)
    (s47 / "report.json").write_text("{broken")

    snapshot = build_snapshot(s46, s47)

    assert snapshot["historical_metrics"] is None


def test_unverified_origin_cannot_be_promoted(tmp_path):
    s46, s47, report46, _ = reports(tmp_path)
    report46["dataset_origin_verified"] = True
    write(s46 / "report.json", report46)

    snapshot = build_snapshot(s46, s47)

    assert snapshot["historical_metrics"] is None


def test_execution_enabled_report_rejected(tmp_path):
    s46, _, report46, _ = reports(tmp_path)
    report46["execution_enabled"] = True
    write(s46 / "report.json", report46)

    result, error = read_latest_report(s46, 46)

    assert result is None
    assert error == "REPORT_SAFETY_FIELDS_INVALID"


def test_bad_metrics_blocked(tmp_path):
    s46, s47, report46, _ = reports(tmp_path)
    report46["metrics"]["wins"] = 200
    write(s46 / "report.json", report46)

    snapshot = build_snapshot(s46, s47)

    assert snapshot["historical_metrics"] is None


def test_metrics_consistency():
    assert valid_metrics(metrics()) is True

    broken = metrics()
    broken["resolved"] = 99

    assert valid_metrics(broken) is False


def test_signal_always_no_trade(tmp_path):
    s46, s47, _, _ = reports(tmp_path)
    snapshot = build_snapshot(s46, s47)

    status, payload = api_response("/api/signal", snapshot)

    assert status == 200
    assert payload["signal"] == "NO TRADE"
    assert payload["execution_enabled"] is False


def test_status_has_no_live_authorization(tmp_path):
    s46, s47, _, _ = reports(tmp_path)
    snapshot = build_snapshot(s46, s47)

    status, payload = api_response("/api/status", snapshot)

    assert status == 200
    assert payload["market_feed"] == "NOT_CONNECTED"
    assert payload["signal_authorized"] is False


def test_health_is_not_market_readiness(tmp_path):
    s46, s47, _, _ = reports(tmp_path)
    snapshot = build_snapshot(s46, s47)

    status, payload = api_response("/api/health", snapshot)

    assert status == 200
    assert payload["status"] == "ONLINE"
    assert payload["market_feed"] == "NOT_CONNECTED"


def test_unknown_route_rejected(tmp_path):
    s46, s47, _, _ = reports(tmp_path)
    snapshot = build_snapshot(s46, s47)

    status, payload = api_response("/api/trade", snapshot)

    assert status == 404
    assert payload["error"] == "NOT_FOUND"
