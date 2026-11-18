"""Offline tests: concurrent prepare, path aliases, invalid claims."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from market_data.credit_refresh_approval import claim_credit_refresh_approval
from market_data.credit_refresh_coordinator import (
    CreditRefreshBindingError,
    prepare_offline_refresh,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def _approved(tmp_path):
    approval = tmp_path / 'approval.json'
    claim_credit_refresh_approval(
        approval_id='test-approval',
        explicitly_approved=True,
        path=approval,
        now=NOW,
    )
    return approval


def test_eight_concurrent_offline_preparations_only_one_succeeds(tmp_path):
    approval = _approved(tmp_path)
    lifecycle = tmp_path / 'lifecycle.json'

    def attempt(_):
        try:
            return prepare_offline_refresh(
                approval_path=approval, lifecycle_path=lifecycle,
                approval_id='test-approval', now=NOW,
            )
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    successes = [result for result in results if result is not None]
    assert len(successes) == 1
    assert successes[0]['offline_only'] is True
    assert successes[0]['status'] == 'CLAIMED'
    assert (tmp_path / 'approval.json.consumed').exists()
    persisted = json.loads(lifecycle.read_text())
    assert persisted['attempt_id'] == successes[0]['attempt_id']


@pytest.mark.parametrize('alias', [
    'approval_alias', 'consumed_alias', 'lock_alias',
])
def test_alias_paths_block_before_consumption(tmp_path, alias):
    approval = _approved(tmp_path)
    (tmp_path / 'subdir').mkdir()
    if alias == 'approval_alias':
        lifecycle = tmp_path / 'subdir' / '..' / 'approval.json'
    elif alias == 'consumed_alias':
        lifecycle = tmp_path / 'subdir' / '..' / 'approval.json.consumed'
    else:
        # Lifecycle lock would resolve to the existing approval file.
        lifecycle = tmp_path / 'lifecycle.json'
        (tmp_path / 'lifecycle.json.lock').symlink_to(approval)

    with pytest.raises(CreditRefreshBindingError):
        prepare_offline_refresh(
            approval_path=approval, lifecycle_path=lifecycle,
            approval_id='test-approval', now=NOW,
        )
    assert not (tmp_path / 'approval.json.consumed').exists()


def test_nonhex_approval_claim_rejected_before_consumption(tmp_path):
    approval = _approved(tmp_path)
    payload = json.loads(approval.read_text())
    payload['claim_id'] = 'z' * 32
    approval.write_text(json.dumps(payload))

    with pytest.raises(CreditRefreshBindingError):
        prepare_offline_refresh(
            approval_path=approval, lifecycle_path=tmp_path / 'lifecycle.json',
            approval_id='test-approval', now=NOW,
        )
    assert not (tmp_path / 'approval.json.consumed').exists()
