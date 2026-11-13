from unittest.mock import patch

from market_data.recovery_inspector import inspect_recovery_state


def test_missing_lock_does_not_create_file(tmp_path):
    provider = tmp_path / "provider.json"
    lock = tmp_path / "provider.json.lock"

    result = inspect_recovery_state(provider)

    assert result.state == "NO_RECOVERY"
    assert not lock.exists()


def test_lock_open_failure_is_inconsistent(tmp_path):
    provider = tmp_path / "provider.json"
    lock = tmp_path / "provider.json.lock"
    lock.touch()

    real_open = open

    def failing_open(path, *args, **kwargs):
        if str(path) == str(lock):
            raise PermissionError("Simulated lock access failure")
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=failing_open):
        result = inspect_recovery_state(provider)

    assert result.state == "INCONSISTENT"


def test_lock_disappears_before_open(tmp_path):
    provider = tmp_path / "provider.json"
    lock = tmp_path / "provider.json.lock"
    lock.touch()

    real_open = open

    def disappearing_open(path, *args, **kwargs):
        if str(path) == str(lock):
            lock.unlink()
            raise FileNotFoundError("Simulated lock disappearance")
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=disappearing_open):
        result = inspect_recovery_state(provider)

    assert result.state == "INCONSISTENT"
    assert not lock.exists()


def test_replaced_lock_inode_is_rejected(tmp_path):
    import os
    import fcntl
    import json
    from unittest.mock import patch

    provider = tmp_path / "provider.json"
    lock = tmp_path / "provider.json.lock"
    marker = tmp_path / "provider.json.recovery_required.json"

    lock.touch()

    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": "a" * 32,
        "authorized_at": "2026-11-13T12:00:00+00:00",
        "credits": 1,
    }))

    real_flock = fcntl.flock
    replaced = False

    def replace_after_lock(fd, operation):
        nonlocal replaced

        result = real_flock(fd, operation)

        if operation == fcntl.LOCK_SH and not replaced:
            replaced = True

            replacement = tmp_path / "replacement.lock"
            replacement.touch()

            os.replace(replacement, lock)

        return result

    with patch(
        "market_data.recovery_inspector.fcntl.flock",
        side_effect=replace_after_lock,
    ):
        result = inspect_recovery_state(provider)

    assert replaced is True
    assert result.state == "INCONSISTENT"
