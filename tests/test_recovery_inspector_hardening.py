import json

from market_data.recovery_inspector import inspect_recovery_state


def test_inspection_does_not_create_lock_file(tmp_path):
    provider = tmp_path / "provider.json"
    lock = tmp_path / "provider.json.lock"

    result = inspect_recovery_state(provider)

    assert result.state == "NO_RECOVERY"
    assert not lock.exists()


def test_corrupt_marker_is_inconsistent(tmp_path):
    (tmp_path / "provider.json.lock").touch()
    provider = tmp_path / "provider.json"
    marker = tmp_path / "provider.json.recovery_required.json"

    marker.write_text("{invalid json")

    result = inspect_recovery_state(provider)

    assert result.state == "INCONSISTENT"


def test_missing_ledger_with_marker_is_uncommitted(tmp_path):
    (tmp_path / "provider.json.lock").touch()
    provider = tmp_path / "provider.json"
    marker = tmp_path / "provider.json.recovery_required.json"

    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": "a" * 32,
        "authorized_at": "2026-11-13T12:00:00+00:00",
        "credits": 1,
    }))

    result = inspect_recovery_state(provider)

    assert result.state == "UNCOMMITTED"


def test_corrupt_ledger_is_inconsistent(tmp_path):
    (tmp_path / "provider.json.lock").touch()
    provider = tmp_path / "provider.json"
    marker = tmp_path / "provider.json.recovery_required.json"
    ledger = tmp_path / "provider.json.reservations.json"

    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": "a" * 32,
        "authorized_at": "2026-11-13T12:00:00+00:00",
        "credits": 1,
    }))

    ledger.write_text("{invalid json")

    result = inspect_recovery_state(provider)

    assert result.state == "INCONSISTENT"
