import os
from unittest.mock import patch

from market_data.unified_request_guard import _save_json_atomic


def test_atomic_save_syncs_parent_directory(tmp_path):
    ledger = tmp_path / "ledger.json"
    events = []

    real_replace = os.replace
    real_fsync = os.fsync

    def tracking_replace(src, dst):
        events.append("replace")
        return real_replace(src, dst)

    def tracking_fsync(fd):
        stat = os.fstat(fd)

        if os.path.isdir(f"/proc/self/fd/{fd}"):
            events.append("directory_fsync")
        else:
            events.append("file_fsync")

        return real_fsync(fd)

    with (
        patch(
            "market_data.unified_request_guard.os.replace",
            side_effect=tracking_replace,
        ),
        patch(
            "market_data.unified_request_guard.os.fsync",
            side_effect=tracking_fsync,
        ),
    ):
        _save_json_atomic(
            ledger,
            {"version": 2, "reserved": 0},
        )

    assert ledger.exists()
    assert "replace" in events
    assert "directory_fsync" in events

    assert events.index("replace") < events.index(
        "directory_fsync"
    )
