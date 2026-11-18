import json
from datetime import datetime, timezone

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request
from market_data.recovery_inspector import inspect_recovery_state


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_authorized_request(tmp_path):
    provider = tmp_path / "provider.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=tmp_path / "budget.json",
        now=NOW,
    )

    return provider, result.request_id


def write_marker(tmp_path, request_id, credits=1, authorized_at=None):
    marker_path = (
        tmp_path / "provider.json.recovery_required.json"
    )

    marker_path.write_text(
        json.dumps({
            "recovery_required": True,
            "reason": "authorization_commit_uncertain",
            "request_id": request_id,
            "authorized_at": authorized_at or NOW.isoformat(),
            "credits": credits,
        }),
        encoding="utf-8",
    )


def test_marker_journal_timestamp_mismatch_is_inconsistent(tmp_path):
    provider, request_id = setup_authorized_request(tmp_path)

    journal_path = (
        tmp_path / "provider.json.authorization_journal.json"
    )

    journal = json.loads(journal_path.read_text())

    journal["transactions"][request_id]["authorized_at"] = (
        "2026-11-13T11:00:00+00:00"
    )

    journal_path.write_text(json.dumps(journal))

    write_marker(tmp_path, request_id)

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "INCONSISTENT"
    assert "journal" in inspection.reason.lower()


def test_marker_unknown_to_existing_journal_is_inconsistent(tmp_path):
    provider, request_id = setup_authorized_request(tmp_path)

    unknown_request_id = "f" * 32

    assert unknown_request_id != request_id

    write_marker(tmp_path, unknown_request_id)

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "INCONSISTENT"
    assert "journal" in inspection.reason.lower()
