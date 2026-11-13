import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.twelve_data_client import (
    MarketDataError,
    reserve_request,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_corrupt_budget_blocks_request(tmp_path):
    budget = tmp_path / "budget.json"
    budget.write_text("{invalid json")

    with pytest.raises(MarketDataError):
        reserve_request(path=budget, now=NOW)

    assert budget.read_text() == "{invalid json"


def test_replace_failure_preserves_old_budget(tmp_path):
    budget = tmp_path / "budget.json"

    original = {
        "minute": "2026-11-13T12:00Z",
        "minute_used": 2,
        "day": "2026-11-13",
        "day_used": 2,
    }

    budget.write_text(json.dumps(original))

    with patch(
        "market_data.twelve_data_client.os.replace",
        side_effect=OSError("Simulated write failure"),
    ):
        with pytest.raises(OSError):
            reserve_request(path=budget, now=NOW)

    assert json.loads(budget.read_text()) == original


def test_existing_empty_budget_fails_closed(tmp_path):
    budget = tmp_path / "budget.json"
    budget.touch()

    with pytest.raises(
        MarketDataError,
        match="empty|corrupt|invalid",
    ):
        reserve_request(path=budget, now=NOW)

    assert budget.read_text() == ""
