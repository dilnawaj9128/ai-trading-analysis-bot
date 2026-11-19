import json
from datetime import datetime, timedelta, timezone

import pytest

from market_data.recovery_case import build_case
from market_data.recovery_approval import (
    RecoveryApprovalBlocked,
    prepare_offline_approval,
    claim_offline_approval,
)


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def fixture_paths(tmp_path, stale=False):
    root = tmp_path / "api"
    root.mkdir()

    evidence = {
        "approved_research_probe.json": {
            "version": 1,
            "attempts": [{
                "status": "UNCERTAIN",
                "started_at": "2026-11-19T13:06:33+00:00",
            }],
        },
        "credit_refresh_execution.json": {
            "status": "UNCERTAIN",
        },
        "credit_refresh_lifecycle.json": {
            "status": "CLAIMED",
        },
        "provider_credits.json": {
            "version": 1,
            "observed_at": (
                NOW - timedelta(minutes=10 if stale else 1)
            ).isoformat(),
            "credits_used": 1,
            "credits_left": 7,
        },
        "twelve_data_budget.json": {
            "minute": NOW.strftime("%Y-%m-%dT%H:%MZ"),
            "minute_used": 0,
            "day": NOW.strftime("%Y-%m-%d"),
            "day_used": 0,
        },
    }

    for filename, payload in evidence.items():
        (root / filename).write_text(json.dumps(payload))

    case = tmp_path / "case.json"
    case.write_text(json.dumps(build_case(root)))

    approval = tmp_path / "approval.json"
    return root, case, approval


def prepare(root, case, approval, approved=True):
    return prepare_offline_approval(
        root=root,
        case_path=case,
        approval_path=approval,
        explicitly_approved=approved,
        now=NOW,
    )


def claim(root, case, approval, now=NOW):
    return claim_offline_approval(
        root=root,
        case_path=case,
        approval_path=approval,
        now=now,
    )


def test_explicit_approval_required(tmp_path):
    root, case, approval = fixture_paths(tmp_path)
    with pytest.raises(RecoveryApprovalBlocked, match="Explicit"):
        prepare(root, case, approval, approved=False)
    assert not approval.exists()


def test_stale_credits_block_preparation(tmp_path):
    root, case, approval = fixture_paths(tmp_path, stale=True)
    with pytest.raises(RecoveryApprovalBlocked, match="preflight"):
        prepare(root, case, approval)
    assert not approval.exists()


def test_single_use_offline_claim(tmp_path):
    root, case, approval = fixture_paths(tmp_path)
    prepared = prepare(root, case, approval)

    marker = claim(root, case, approval)

    assert prepared["http_authorized"] is False
    assert marker["status"] == "CONSUMED_OFFLINE"
    assert marker["http_authorized"] is False

    with pytest.raises(RecoveryApprovalBlocked, match="consumed"):
        claim(root, case, approval)


def test_approval_cannot_be_prepared_twice(tmp_path):
    root, case, approval = fixture_paths(tmp_path)
    prepare(root, case, approval)

    with pytest.raises(RecoveryApprovalBlocked, match="already"):
        prepare(root, case, approval)


def test_expired_approval_blocked(tmp_path):
    root, case, approval = fixture_paths(tmp_path)
    prepare(root, case, approval)

    with pytest.raises(RecoveryApprovalBlocked, match="expired"):
        claim(
            root, case, approval,
            now=NOW + timedelta(minutes=3),
        )

    assert not (tmp_path / "approval.json.consumed").exists()


def test_case_tampering_blocks_claim(tmp_path):
    root, case, approval = fixture_paths(tmp_path)
    prepare(root, case, approval)

    data = json.loads(case.read_text())
    data["classification"] = "VERIFIED"
    case.write_text(json.dumps(data))

    with pytest.raises(RecoveryApprovalBlocked, match="changed"):
        claim(root, case, approval)


def test_old_uncertain_probe_preserved(tmp_path):
    root, case, approval = fixture_paths(tmp_path)
    probe = root / "approved_research_probe.json"

    before = probe.read_bytes()

    prepare(root, case, approval)
    claim(root, case, approval)

    assert probe.read_bytes() == before
    assert json.loads(probe.read_text())["attempts"][-1][
        "status"
    ] == "UNCERTAIN"


def test_provider_evidence_change_blocks_claim(tmp_path):
    root, case, approval = fixture_paths(tmp_path)
    prepare(root, case, approval)

    provider = root / "provider_credits.json"
    data = json.loads(provider.read_text())
    data["credits_left"] = 0
    provider.write_text(json.dumps(data))

    with pytest.raises(RecoveryApprovalBlocked, match="preflight"):
        claim(root, case, approval)
