"""Historical request failure must preserve uncertain reservations."""

import json

import pandas as pd
import pytest
from unittest.mock import Mock

from config.market_config import create_research_config
from market_data.historical_collector import fetch_historical_candles
from market_data.provider_credit_state import save_credit_state
from market_data.api_credit_monitor import CreditSnapshot
from market_data.twelve_data_client import MarketDataError


NOW = pd.Timestamp("2026-11-18T12:00:00Z")


def test_missing_credit_headers_preserves_reservation(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=1,
            credits_left=7,
            low_credits=False,
            information_available=True,
        ),
        path=provider,
        now=NOW.to_pydatetime(),
    )

    response = Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.headers = {}
    response.json.return_value = {
        "meta": {"symbol": "EUR/USD", "interval": "1min"},
        "values": [{
            "datetime": "2026-11-18 10:00:00",
            "open": "1.1000",
            "high": "1.1010",
            "low": "1.0990",
            "close": "1.1005",
        }],
    }

    session = Mock()
    session.get.return_value = response

    config = create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )

    with pytest.raises(
        MarketDataError,
        match="Provider credit snapshot update failed",
    ):
        fetch_historical_candles(
            config,
            start=pd.Timestamp("2026-11-18T10:00:00Z"),
            end=pd.Timestamp("2026-11-18T10:01:00Z"),
            now=NOW,
            api_key="fake-key",
            state_path=budget,
            provider_credit_path=provider,
            session=session,
            outputsize=10,
        )

    ledger = provider.with_name(
        provider.name + ".reservations.json"
    )

    data = json.loads(ledger.read_text())
    requests = data["requests"]

    assert len(requests) == 1

    reservation = next(iter(requests.values()))

    assert reservation["status"] == "UNCERTAIN"
    assert reservation["credits"] == 1
    assert data["reserved"] == 1

    session.get.assert_called_once()
