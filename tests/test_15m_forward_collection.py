"""No-network 15-minute prospective collection gate tests."""
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from scripts.run_15m_forward_collection import eligibility, offline_progress


def _scorecard():
    return {"counts": {"WIN": 0, "LOSS": 0, "PUSH": 0, "ABSTAINED": 3},
            "invalid_evidence": []}


def test_uncertain_provider_attempt_blocks_live_even_with_fresh_snapshot(tmp_path):
    provider = tmp_path / "provider_credits.json"
    ledger = provider.with_name(provider.name + ".reservations.json")
    ledger.write_text(json.dumps({
        "version": 2, "reserved": 1, "legacy_reserved": 0,
        "requests": {"abc": {"status": "UNCERTAIN", "credits": 1}},
    }))
    with patch("research.real_prediction_campaign.prospective_scorecard", return_value=_scorecard()), \
         patch("research.real_prediction_campaign.preflight_observation_window", return_value={"eligible": True}), \
         patch("market_data.provider_credit_state.load_credit_state", return_value=object()):
        result = eligibility(provider=provider, journal=tmp_path / "campaign",
                             now=datetime(2026,11,24,tzinfo=timezone.utc))
    assert result["status"] == "BLOCKED"
    assert result["outstanding_reserved"] == 1
    assert result["uncertain_requests"] == 1
    assert "UNCERTAIN_PROVIDER_REQUESTS_REQUIRE_RECONCILIATION" in result["reasons"]
    assert result["observed_nonpush"] == 0
    assert result["remaining_nonpush"] == 100


def test_unresolved_renewal_blocks_even_with_settled_ledger(tmp_path):
    provider = tmp_path / "provider_credits.json"
    ledger = provider.with_name(provider.name + ".reservations.json")
    ledger.write_text(json.dumps({"version":2,"reserved":0,
                                  "legacy_reserved":0,"requests":{}}))
    (tmp_path / "verified_credit_renewals.json").write_text(json.dumps({
        "version": 1, "attempts": [{"request_id":"abc","status":"UNCERTAIN"}],
    }))
    with patch("research.real_prediction_campaign.prospective_scorecard", return_value=_scorecard()), \
         patch("research.real_prediction_campaign.preflight_observation_window", return_value={"eligible": True}), \
         patch("market_data.provider_credit_state.load_credit_state", return_value=object()):
        result = eligibility(provider=provider, journal=tmp_path / "campaign")
    assert "CREDIT_RENEWAL_UNRESOLVED" in result["reasons"]
    assert result["status"] == "BLOCKED"


def test_absent_fresh_snapshot_blocks(tmp_path):
    provider = tmp_path / "provider_credits.json"
    provider.with_name(provider.name + ".reservations.json").write_text(json.dumps({
        "version":2, "reserved":0, "legacy_reserved":0, "requests":{},
    }))
    with patch("research.real_prediction_campaign.prospective_scorecard", return_value=_scorecard()), \
         patch("research.real_prediction_campaign.preflight_observation_window", return_value={"eligible": True}), \
         patch("market_data.provider_credit_state.load_credit_state", return_value=None):
        result = eligibility(provider=provider, journal=tmp_path / "campaign")
    assert "CREDIT_SNAPSHOT_STALE_OR_MISSING" in result["reasons"]


def test_offline_summary_cannot_fabricate_outcomes(tmp_path):
    with patch("scripts.run_accuracy_all.archive_settlement_pass",
               return_value={"captures_found": 0, "new_settlements": []}), \
         patch("scripts.run_15m_forward_collection.eligibility",
               return_value={"observed_nonpush": 0, "remaining_nonpush": 100}):
        report = offline_progress(journal=tmp_path, provider=tmp_path / "provider")
    assert report["new_provider_requests"] == 0
    assert report["broker_orders"] == 0
    assert report["accuracy_verified"] is False
    assert report["readiness"]["observed_nonpush"] == 0


def test_successful_legacy_capture_normalized_without_crashing():
    from scripts.run_15m_forward_collection import _normalize_live_outcome
    legacy = {
        "observation": "data/research/prospective_accuracy/observations/abc.json",
        "saved_csv": "data/research/prospective_accuracy/captures/abc.csv",
        "source_sha256": "a" * 64,
        "expiry_utc": "2026-11-24T17:00:00+00:00",
        "research_hypothesis": "DOWN",
        "renewal_used": False,
        "live_signal": "NO TRADE",
        "broker_orders": 0,
    }
    outcome = _normalize_live_outcome(legacy)
    assert outcome["status"] == "OBSERVATION_RECORDED"
    assert outcome["provider_requests"] == 1
    assert outcome["research_hypothesis"] == "DOWN"
    assert "status" not in legacy  # evidence not mutated


def test_successful_capture_with_renewal_counts_two_requests():
    from scripts.run_15m_forward_collection import _normalize_live_outcome
    outcome = _normalize_live_outcome({
        "observation": "observations/a.json", "saved_csv": "captures/a.csv",
        "source_sha256": "b" * 64,
        "expiry_utc": "2026-11-24T17:00:00+00:00",
        "renewal_used": True,
    })
    assert outcome["status"] == "OBSERVATION_RECORDED"
    assert outcome["provider_requests"] == 2


def test_failed_http_does_not_falsely_count_zero():
    from scripts.run_15m_forward_collection import _normalize_live_outcome
    outcome = _normalize_live_outcome({
        "status": "BLOCKED_OR_FAILED", "exception_type": "ConnectionError"
    })
    assert outcome["status"] == "BLOCKED_OR_FAILED"
    assert outcome["provider_requests"] == "UNKNOWN_REVIEW_JOURNALS"


def test_blocked_without_http_counts_zero():
    from scripts.run_15m_forward_collection import _normalize_live_outcome
    outcome = _normalize_live_outcome({
        "status": "BLOCKED_NO_HTTP",
        "reason": "15_MINUTE_NONOVERLAP_WINDOW",
    })
    assert outcome["provider_requests"] == 0
