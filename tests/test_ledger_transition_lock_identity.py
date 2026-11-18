import os
from unittest.mock import patch

import pytest

from market_data.authorization_ledger import transition_authorization


def test_transition_rejects_replaced_lock_file(tmp_path):
    provider = tmp_path / "provider.json"
    ledger = tmp_path / "provider.json.reservations.json"
    lock = tmp_path / "provider.json.lock"

    ledger.write_text(
        '{"version":2,"reserved":1,"legacy_reserved":0,'
        '"requests":{"request-1":{"credits":1,'
        '"status":"PENDING",'
        '"authorized_at":"2026-11-13T12:00:00+00:00",'
        '"snapshot_observed_at":"2026-11-13T12:00:00+00:00"}}}'
    )

    original_flock = __import__("fcntl").flock

    def replace_lock(fd, operation):
        result = original_flock(fd, operation)

        if operation == __import__("fcntl").LOCK_EX:
            os.unlink(lock)
            lock.touch()

        return result

    with patch(
        "market_data.authorization_ledger.fcntl.flock",
        side_effect=replace_lock,
    ):
        with pytest.raises(RuntimeError, match="lock identity"):
            transition_authorization(
                provider_state_path=provider,
                request_id="request-1",
                status="UNCERTAIN",
            )

    # Ledger must remain unchanged.
    assert '"status":"PENDING"' in ledger.read_text()
