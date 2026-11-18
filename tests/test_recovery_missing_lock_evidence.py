import json

from market_data.recovery_inspector import inspect_recovery_state


def test_missing_lock_with_authorization_history_is_inconsistent(tmp_path):
    provider = tmp_path / "provider.json"
    history = tmp_path / "provider.json.authorization_history.json"
    lock = tmp_path / "provider.json.lock"

    history.write_text(
        json.dumps({"version": 1, "initialized": True}),
        encoding="utf-8",
    )

    before = history.read_bytes()

    result = inspect_recovery_state(provider)

    assert result.state == "INCONSISTENT"
    assert "lock" in result.reason.lower()

    # Read-only inspection must not create a lock.
    assert not lock.exists()
    assert history.read_bytes() == before


def test_fresh_directory_without_lock_is_no_recovery(tmp_path):
    provider = tmp_path / "provider.json"

    result = inspect_recovery_state(provider)

    assert result.state == "NO_RECOVERY"
    assert not (
        tmp_path / "provider.json.lock"
    ).exists()
