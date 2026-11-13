from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from config.market_config import create_research_config
from market_data.api_credit_monitor import CreditSnapshot
from market_data.historical_collector import fetch_historical_candles
from market_data.provider_credit_guard import ProviderCreditLimitReached
from market_data.provider_credit_state import (
    load_credit_state,
    save_credit_state,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def make_config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def make_state(path, left):
    save_credit_state(
        CreditSnapshot(
            credits_used=1,
            credits_left=left,
            low_credits=left < 20,
            information_available=True,
        ),
        path=path,
        now=NOW,
    )


def make_response():
    response = Mock()
    response.raise_for_status.return_value = None
    response.headers = {
        "api-credits-used": "2",
        "api-credits-left": "98",
    }
    response.json.return_value = {
        "meta": {
            "symbol": "EUR/USD",
            "interval": "1min",
        },
        "values": [{
            "datetime": "2026-11-12 10:00:00",
            "open": "1.1000",
            "high": "1.1010",
            "low": "1.0990",
            "close": "1.1005",
        }],
    }
    return response


def fetch(session, provider_path, budget_path):
    return fetch_historical_candles(
        make_config(),
        start=pd.Timestamp("2026-11-12T10:00:00Z"),
        end=pd.Timestamp("2026-11-12T10:01:00Z"),
        now=pd.Timestamp(NOW),
        api_key="test-key",
        session=session,
        state_path=budget_path,
        provider_credit_path=provider_path,
        outputsize=10,
    )


def test_guarded_request_refreshes_credits(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    make_state(provider, 100)

    session = Mock()
    session.get.return_value = make_response()

    result = fetch(session, provider, budget)

    assert result["candles"] == 1
    assert result["credit_snapshot"].credits_left == 98
    assert load_credit_state(
        path=provider, now=NOW
    ).credits_left == 98

    assert session.get.call_count == 1

    import json
    state = json.loads(budget.read_text())
    assert state["minute_used"] == 1
    assert state["day_used"] == 1


def test_insufficient_credits_blocks_http(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    make_state(provider, 10)

    session = Mock()

    with pytest.raises(ProviderCreditLimitReached):
        fetch(session, provider, budget)

    session.get.assert_not_called()
    assert not budget.exists()
