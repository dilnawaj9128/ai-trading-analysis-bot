"""Regression checks for 3-in-1 runner. Only isolated filesystem and mocks."""
import json
from pathlib import Path
from unittest.mock import patch

from scripts.run_three_in_one_verification import run
from scripts.local_deployment_smoke import backend_smoke, streamlit_smoke

def test_local_backend_http_smoke():
    r = backend_smoke()
    assert r["status"] == "LOCAL_BACKEND_SMOKE_PASSED"
    assert r["checks"]["/api/health"]
    assert r["checks"]["/api/signal"]
    assert r["checks"]["POST /api/signal blocked"]
    assert r["remote_production_deployment_verified"] is False

def test_absent_streamlit_not_production(monkeypatch):
    with patch("scripts.local_deployment_smoke.importlib.util.find_spec", return_value=None):
        r = streamlit_smoke(seconds=1)
    assert r["status"] == "STREAMLIT_NOT_INSTALLED"
    assert r["remote_production_deployment_verified"] is False

def test_all_three_offline_is_single_report_and_no_live_call(tmp_path):
    def _no_network(*args, **kwargs):
        raise AssertionError("No live fetch permitted")
    with patch("scripts.run_three_in_one_verification._safe_reconcile",
               return_value={"status": "RECONCILED", "outstanding_reserved": 18}), \
         patch("scripts.run_three_in_one_verification.reservation_audit",
               return_value={"outstanding_reserved": 18}), \
         patch("scripts.run_three_in_one_verification.archive_settlement_pass",
               return_value={"pending": []}), \
         patch("scripts.run_three_in_one_verification.prospective_scorecard",
               return_value={"counts": {"WIN": 0, "LOSS": 0, "ABSTAINED": 3, "PUSH": 0},
                             "statistical_audit": {"status": "NO_OUTCOMES"}}), \
         patch("scripts.run_three_in_one_verification.deployment_smoke",
               return_value={"status": "LOCAL_SMOKE_PASSED_PRODUCTION_NOT_VERIFIED"}), \
         patch("scripts.run_real_prediction_live_once.capture_live_once", _no_network):
        report, file = run(journal=tmp_path / "journal", output=tmp_path / "reports")
    assert file.exists()
    assert report["task_1_forward_collection"]["bounded_live_attempt"]["status"] == "NOT_REQUESTED"
    assert report["task_1_forward_collection"]["prospective_nonpush"] == 0
    assert report["task_2_receipt_bound_credit_review"]["no_ledger_reset_or_unverified_release"]
    assert report["broker_orders"] == 0
    assert json.loads(file.read_text())["live_trade_signal"] == "NO TRADE"

def test_live_missing_key_has_no_request(tmp_path):
    with patch("scripts.run_three_in_one_verification._safe_reconcile",
               return_value={"status": "RECONCILED"}), \
         patch("scripts.run_three_in_one_verification.reservation_audit",
               return_value={"outstanding_reserved": 18}), \
         patch("scripts.run_three_in_one_verification.archive_settlement_pass",
               return_value={}), \
         patch("scripts.run_three_in_one_verification.prospective_scorecard",
               return_value={"counts": {"WIN": 0, "LOSS": 0},
                             "statistical_audit": {}}):
        report, file = run(journal=tmp_path, output=tmp_path,
                           one_live_fetch=True, api_key=None, smoke=False)
    assert report["task_1_forward_collection"]["bounded_live_attempt"]["status"] == "BLOCKED_API_KEY_MISSING"
    assert report["broker_orders"] == 0
