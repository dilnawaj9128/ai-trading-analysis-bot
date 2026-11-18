"""Concurrency and safety tests for manual credit refresh."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest

from market_data.manual_credit_refresh import (
    ManualRefreshBlocked,
    manual_credit_refresh,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def make_args(tmp_path, callback):
    return {
        "request_callback": callback,
        "approval_id": "test-approval-21y",
        "explicitly_approved": True,
        "provider_path": tmp_path / "provider.json",
        "budget_path": tmp_path / "budget.json",
        "now": NOW,
    }


def response():
    return SimpleNamespace(
        status_code=200,
        json=lambda: {
            "status": "ok",
            "values": [{"datetime": "2026-11-18 11:59:00"}],
        },
        headers={
            "api-credits-used": "1",
            "api-credits-left": "7",
        },
    )


def test_two_concurrent_requests_only_one_executes(tmp_path):
    barrier = Barrier(2)
    lock = Lock()
    calls = []

    def callback():
        with lock:
            calls.append("executed")
        return response()

    args = make_args(tmp_path, callback)

    def attempt():
        barrier.wait(timeout=5)
        try:
            result = manual_credit_refresh(**args)
            return result["status"]
        except ManualRefreshBlocked:
            return "BLOCKED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(attempt)
            for _ in range(2)
        ]
        statuses = [future.result() for future in futures]

    assert sorted(statuses) == [
        "BLOCKED",
        "SNAPSHOT_REFRESHED",
    ]
    assert calls == ["executed"]

    budget = json.loads(
        (tmp_path / "budget.json").read_text()
    )
    assert budget["day_used"] == 1


def test_existing_recovery_marker_blocks_request(tmp_path):
    provider = tmp_path / "provider.json"
    recovery = tmp_path / "provider.json.recovery_required.json"
    recovery.write_text("recovery required")

    called = []

    def callback():
        called.append(True)
        return response()

    with pytest.raises(
        ManualRefreshBlocked,
        match="Existing authorization or recovery evidence",
    ):
        manual_credit_refresh(**make_args(tmp_path, callback))

    assert called == []
    assert not (
        tmp_path / "provider.json.manual_refresh_claim.json"
    ).exists()


def test_failed_request_cannot_be_retried(tmp_path):
    called = []

    def failing_callback():
        called.append(True)
        raise TimeoutError("Simulated timeout")

    args = make_args(tmp_path, failing_callback)

    first = manual_credit_refresh(**args)

    assert first["status"] == "UNCERTAIN"

    with pytest.raises(
        ManualRefreshBlocked,
        match="already attempted",
    ):
        manual_credit_refresh(**args)

    assert len(called) == 1
