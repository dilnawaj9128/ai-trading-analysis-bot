import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from config.market_config import create_research_config
from market_data.api_credit_monitor import CreditSnapshot
from market_data.historical_collector import fetch_historical_candles
from market_data.provider_credit_state import (
    load_credit_state,
    save_credit_state,
)
from market_data.twelve_data_client import MarketDataError


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_paths(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=0,
            credits_left=100,
            low_credits=False,
            information_available=True,
        ),
        path=provider,
        now=NOW,
    )

    return provider, budget


def fetch(session, provider, budget):
    config = create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )

    return fetch_historical_candles(
        config,
        start="2026-11-12T10:00:00Z",
        end="2026-11-12T10:01:00Z",
        now=NOW,
        api_key="mock-key",
        session=session,
        state_path=budget,
        provider_credit_path=provider,
        outputsize=10,
    )


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_http_error_preserves_credit_state(tmp_path, status):
    provider, budget = setup_paths(tmp_path)

    response = requests.Response()
    response.status_code = status
    response.url = "https://api.twelvedata.com/time_series"

    session = Mock()
    session.get.return_value = response

    with pytest.raises(MarketDataError):
        fetch(session, provider, budget)

    assert load_credit_state(
        path=provider,
        now=NOW,
    ).credits_left == 100

    state = json.loads(budget.read_text())
    assert state["minute_used"] == 1
    assert state["day_used"] == 1

    session.get.assert_called_once()


def test_network_failure_preserves_credit_state(tmp_path):
    provider, budget = setup_paths(tmp_path)

    session = Mock()
    session.get.side_effect = requests.ConnectionError(
        "Simulated network failure"
    )

    with pytest.raises(MarketDataError, match="network error"):
        fetch(session, provider, budget)

    assert load_credit_state(
        path=provider,
        now=NOW,
    ).credits_left == 100

    state = json.loads(budget.read_text())
    assert state["minute_used"] == 1

    session.get.assert_called_once()


def test_invalid_json_preserves_credit_state(tmp_path):
    provider, budget = setup_paths(tmp_path)

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("Invalid JSON")
    response.headers = {}

    session = Mock()
    session.get.return_value = response

    with pytest.raises(MarketDataError, match="invalid JSON"):
        fetch(session, provider, budget)

    assert load_credit_state(
        path=provider,
        now=NOW,
    ).credits_left == 100
