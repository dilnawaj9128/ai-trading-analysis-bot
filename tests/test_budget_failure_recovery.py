import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.twelve_data_client import reserve_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def initial_budget():
    return {
        "minute": "2026-11-13T12:00Z",
        "minute_used": 2,
        "day": "2026-11-13",
        "day_used": 2,
    }


def test_replace_failure_keeps_old_budget(tmp_path):
    budget = tmp_path / "budget.json"
    original = initial_budget()
    budget.write_text(json.dumps(original))

    with patch(
        "market_data.twelve_data_client.os.replace",
        side_effect=OSError("replace failed"),
    ):
        with pytest.raises(OSError, match="replace failed"):
            reserve_request(path=budget, now=NOW)

    assert json.loads(budget.read_text()) == original


def test_directory_sync_failure_is_not_silent(tmp_path):
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps(initial_budget()))

    real_fsync = os.fsync

    def fail_directory_sync(fd):
        if os.path.isdir(f"/proc/self/fd/{fd}"):
            raise OSError("directory sync failed")
        return real_fsync(fd)

    with patch(
        "market_data.twelve_data_client.os.fsync",
        side_effect=fail_directory_sync,
    ):
        with pytest.raises(
            OSError,
            match="directory sync failed",
        ):
            reserve_request(path=budget, now=NOW)


def test_failed_replace_cleans_temporary_files(tmp_path):
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps(initial_budget()))

    with patch(
        "market_data.twelve_data_client.os.replace",
        side_effect=OSError("replace failed"),
    ):
        with pytest.raises(OSError):
            reserve_request(path=budget, now=NOW)

    assert list(tmp_path.glob(".budget_*.tmp")) == []
