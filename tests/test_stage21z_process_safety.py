"""Cross-process safety tests for manual credit refresh."""

import json
import multiprocessing as mp
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from market_data.manual_credit_refresh import (
    ManualRefreshBlocked,
    manual_credit_refresh,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def fake_response():
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


def run_refresh(root):
    return manual_credit_refresh(
        request_callback=fake_response,
        approval_id="process-test",
        explicitly_approved=True,
        provider_path=Path(root) / "provider.json",
        budget_path=Path(root) / "budget.json",
        now=NOW,
    )


def process_worker(root, start_event, results):
    start_event.wait(timeout=10)

    try:
        result = run_refresh(root)
        results.put(result["status"])
    except ManualRefreshBlocked:
        results.put("BLOCKED")


def crash_callback():
    os._exit(23)


def crash_worker(root):
    manual_credit_refresh(
        request_callback=crash_callback,
        approval_id="crash-test",
        explicitly_approved=True,
        provider_path=Path(root) / "provider.json",
        budget_path=Path(root) / "budget.json",
        now=NOW,
    )


def test_two_processes_only_one_refreshes(tmp_path):
    ctx = mp.get_context("spawn")
    start = ctx.Event()
    results = ctx.Queue()

    processes = [
        ctx.Process(
            target=process_worker,
            args=(str(tmp_path), start, results),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()

    start.set()

    try:
        for process in processes:
            process.join(timeout=15)
            assert not process.is_alive()
            assert process.exitcode == 0

        statuses = sorted([
            results.get(timeout=3)
            for _ in processes
        ])

        assert statuses == [
            "BLOCKED",
            "SNAPSHOT_REFRESHED",
        ]

        budget = json.loads(
            (tmp_path / "budget.json").read_text()
        )

        assert budget["day_used"] == 1

    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)


def test_crash_preserves_claim_and_blocks_retry(tmp_path):
    ctx = mp.get_context("spawn")

    process = ctx.Process(
        target=crash_worker,
        args=(str(tmp_path),),
    )

    process.start()

    try:
        process.join(timeout=15)
        assert not process.is_alive()
        assert process.exitcode == 23

        claim = (
            tmp_path /
            "provider.json.manual_refresh_claim.json"
        )

        assert claim.exists()

        try:
            run_refresh(tmp_path)
        except ManualRefreshBlocked:
            pass
        else:
            raise AssertionError(
                "Retry after crash was incorrectly allowed"
            )

        assert not (tmp_path / "provider.json").exists()

    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
