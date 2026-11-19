import json
from datetime import datetime, timezone

from market_data.manual_credit_refresh import inspect_production_credit_refresh

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


def args(tmp_path):
    return dict(
        provider_path=tmp_path / "provider.json",
        budget_path=tmp_path / "budget.json",
        approval_path=tmp_path / "approval.json",
        lifecycle_path=tmp_path / "lifecycle.json",
        execution_path=tmp_path / "execution.json",
        now=NOW,
        api_key_present=True,
    )


def test_clean_preflight_is_read_only(tmp_path):
    result = inspect_production_credit_refresh(**args(tmp_path))
    assert result["ready_for_one_approved_request"] is True
    assert result["live_fetch_authorized"] is False
    assert list(tmp_path.iterdir()) == []


def test_prior_reservations_block(tmp_path):
    values = args(tmp_path)
    (tmp_path / "provider.json.reservations.json").write_text("{}")
    result = inspect_production_credit_refresh(**values)
    assert result["ready_for_one_approved_request"] is False
    assert "authorization/recovery" in " ".join(result["reasons"])


def test_existing_approval_blocks(tmp_path):
    values = args(tmp_path)
    (tmp_path / "approval.json").write_text("{}")
    result = inspect_production_credit_refresh(**values)
    assert not result["ready_for_one_approved_request"]


def test_exhausted_budget_blocks(tmp_path):
    values = args(tmp_path)
    (tmp_path / "budget.json").write_text(json.dumps({
        "minute": "2026-11-18T12:00Z", "minute_used": 8,
        "day": "2026-11-18", "day_used": 800,
    }))
    result = inspect_production_credit_refresh(**values)
    assert not result["ready_for_one_approved_request"]
    assert "Local daily budget exhausted" in result["reasons"]


def test_missing_key_blocks(tmp_path):
    values = args(tmp_path)
    values["api_key_present"] = False
    result = inspect_production_credit_refresh(**values)
    assert not result["ready_for_one_approved_request"]
