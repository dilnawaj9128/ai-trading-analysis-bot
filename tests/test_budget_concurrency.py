import json
from multiprocessing import get_context
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

from market_data.twelve_data_client import (
    BudgetExceeded,
    reserve_request,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def attempt_reservation(path):
    try:
        reserve_request(path=path, now=NOW)
        return "RESERVED"
    except BudgetExceeded:
        return "BLOCKED"


def test_concurrent_requests_respect_minute_limit(tmp_path):
    budget = tmp_path / "budget.json"

    with ProcessPoolExecutor(
        max_workers=4,
        mp_context=get_context("spawn"),
    ) as executor:
        results = list(
            executor.map(
                attempt_reservation,
                [budget] * 16,
            )
        )

    assert results.count("RESERVED") == 8
    assert results.count("BLOCKED") == 8

    state = json.loads(budget.read_text())

    assert state["minute_used"] == 8
    assert state["day_used"] == 8


def test_sequential_requests_preserve_counters(tmp_path):
    budget = tmp_path / "budget.json"

    for expected in range(1, 5):
        result = reserve_request(path=budget, now=NOW)

        assert result["minute_used"] == expected
        assert result["day_used"] == expected

    state = json.loads(budget.read_text())

    assert state["minute_used"] == 4
    assert state["day_used"] == 4
