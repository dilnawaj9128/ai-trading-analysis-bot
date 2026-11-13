import json
from datetime import datetime, timezone

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request
from market_data.recovery_inspector import inspect_recovery_state


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_provider(tmp_path):
    provider = tmp_path / "provider.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    (tmp_path / "provider.json.lock").touch()
    return provider


def test_no_recovery_marker(tmp_path):
    provider = setup_provider(tmp_path)

    result = inspect_recovery_state(provider)

    assert result.state == "NO_RECOVERY"


def test_uncommitted_recovery(tmp_path):
    provider = setup_provider(tmp_path)

    marker = tmp_path / "provider.json.recovery_required.json"
    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": "a" * 32,
        "authorized_at": NOW.isoformat(),
        "credits": 1,
    }))

    result = inspect_recovery_state(provider)

    assert result.state == "UNCOMMITTED"


def test_committed_recovery(tmp_path):
    provider = setup_provider(tmp_path)

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=tmp_path / "budget.json",
        now=NOW,
    )

    marker = tmp_path / "provider.json.recovery_required.json"
    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": result.request_id,
        "authorized_at": NOW.isoformat(),
        "credits": 1,
    }))

    inspected = inspect_recovery_state(provider)

    assert inspected.state == "COMMITTED"


def test_inconsistent_recovery(tmp_path):
    provider = setup_provider(tmp_path)

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=tmp_path / "budget.json",
        now=NOW,
    )

    marker = tmp_path / "provider.json.recovery_required.json"
    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": result.request_id,
        "authorized_at": NOW.isoformat(),
        "credits": 5,
    }))

    inspected = inspect_recovery_state(provider)

    assert inspected.state == "INCONSISTENT"
