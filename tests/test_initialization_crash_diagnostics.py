import json

from market_data.recovery_inspector import inspect_recovery_state


def test_history_only_initialization_is_inconsistent(tmp_path):
    provider = tmp_path / "provider.json"

    history = tmp_path / "provider.json.authorization_history.json"
    lock = tmp_path / "provider.json.lock"

    history.write_text(
        json.dumps({"version": 1, "initialized": True})
    )
    lock.touch()

    before_history = history.read_bytes()

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "INCONSISTENT"
    assert "initialization" in inspection.reason.lower()

    # Inspection must remain read-only.
    assert history.read_bytes() == before_history
    assert not (
        tmp_path / "provider.json.authorization_journal.json"
    ).exists()
    assert not (
        tmp_path / "provider.json.reservations.json"
    ).exists()
    assert not (
        tmp_path / "provider.json.recovery_required.json"
    ).exists()
