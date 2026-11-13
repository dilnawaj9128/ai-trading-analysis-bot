import os
from datetime import datetime, timezone
from unittest.mock import patch

from market_data.twelve_data_client import reserve_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_budget_save_uses_atomic_replace(tmp_path):
    budget = tmp_path / "budget.json"

    real_replace = os.replace
    replaced = []

    def tracking_replace(src, dst):
        replaced.append((str(src), str(dst)))
        return real_replace(src, dst)

    with patch(
        "market_data.twelve_data_client.os.replace",
        side_effect=tracking_replace,
    ):
        reserve_request(path=budget, now=NOW)

    assert budget.exists()
    assert any(dst == str(budget) for _, dst in replaced)


def test_budget_save_syncs_parent_directory(tmp_path):
    budget = tmp_path / "budget.json"

    real_replace = os.replace
    real_fsync = os.fsync
    events = []

    def tracking_replace(src, dst):
        events.append("replace")
        return real_replace(src, dst)

    def tracking_fsync(fd):
        if os.path.isdir(f"/proc/self/fd/{fd}"):
            events.append("directory_fsync")
        else:
            events.append("file_fsync")

        return real_fsync(fd)

    with (
        patch(
            "market_data.twelve_data_client.os.replace",
            side_effect=tracking_replace,
        ),
        patch(
            "market_data.twelve_data_client.os.fsync",
            side_effect=tracking_fsync,
        ),
    ):
        reserve_request(path=budget, now=NOW)

    assert "file_fsync" in events
    assert "replace" in events
    assert "directory_fsync" in events

    assert events.index("file_fsync") < events.index("replace")
    assert events.index("replace") < events.index("directory_fsync")


def test_budget_uses_separate_stable_lock(tmp_path):
    budget = tmp_path / "budget.json"
    lock = tmp_path / "budget.json.lock"

    reserve_request(path=budget, now=NOW)

    assert budget.exists()
    assert lock.exists()

    assert os.stat(budget).st_ino != os.stat(lock).st_ino
