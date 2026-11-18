from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from market_data.credit_refresh_store import (
    CreditRefreshStoreError,
    _claim_refresh_attempt_internal,
    transition_refresh_attempt,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def claim(path, now=NOW):
    return _claim_refresh_attempt_internal(path=path, now=now)


def test_first_claim(tmp_path):
    result = claim(tmp_path / "state.json")
    assert result["status"] == "CLAIMED"


def test_duplicate_claim_blocked(tmp_path):
    path = tmp_path / "state.json"
    claim(path)

    with pytest.raises(CreditRefreshStoreError):
        claim(path)


def test_restart_preserves_claim(tmp_path):
    path = tmp_path / "state.json"
    claim(path)

    with pytest.raises(CreditRefreshStoreError):
        claim(path, NOW + timedelta(hours=2))


def test_uncertain_blocks_retry(tmp_path):
    path = tmp_path / "state.json"
    result = claim(path)

    transition_refresh_attempt(
        path=path,
        attempt_id=result["attempt_id"],
        status="UNCERTAIN",
    )

    with pytest.raises(CreditRefreshStoreError):
        claim(path, NOW + timedelta(days=1))


def test_completed_cooldown():
    from market_data.credit_refresh_lifecycle import (
        evaluate_refresh_lifecycle,
    )

    decision = evaluate_refresh_lifecycle(
        last_attempt_at=NOW,
        last_status="COMPLETED",
        now=NOW + timedelta(minutes=10),
        cooldown_seconds=3600,
    )

    assert decision.allowed is False


def test_completed_after_cooldown():
    from market_data.credit_refresh_lifecycle import (
        evaluate_refresh_lifecycle,
    )

    decision = evaluate_refresh_lifecycle(
        last_attempt_at=NOW,
        last_status="COMPLETED",
        now=NOW + timedelta(hours=2),
        cooldown_seconds=3600,
    )

    assert decision.allowed is True


def test_corrupt_state_blocks(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{broken")

    with pytest.raises(CreditRefreshStoreError):
        claim(path)


def test_concurrent_claim_only_one_succeeds(tmp_path):
    path = tmp_path / "state.json"

    def attempt(_):
        try:
            claim(path)
            return "SUCCESS"
        except CreditRefreshStoreError:
            return "BLOCKED"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(8)))

    assert results.count("SUCCESS") == 1
    assert results.count("BLOCKED") == 7
