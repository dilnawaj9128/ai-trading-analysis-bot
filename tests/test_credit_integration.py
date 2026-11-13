from unittest.mock import Mock, patch

import pandas as pd

from config.market_config import create_research_config
from market_data.historical_collector import fetch_historical_candles


def test_credit_snapshot_returned():
    config = create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )

    response = Mock()
    response.raise_for_status.return_value = None
    response.headers = {
        "api-credits-used": "1",
        "api-credits-left": "799",
    }

    response.json.return_value = {
        "meta": {
            "symbol": "EUR/USD",
            "interval": "1min",
        },
        "values": [
            {
                "datetime": "2026-11-12 10:00:00",
                "open": "1.1000",
                "high": "1.1010",
                "low": "1.0990",
                "close": "1.1005",
            }
        ],
    }

    session = Mock()
    session.get.return_value = response

    with patch("market_data.historical_collector.reserve_request"):
        result = fetch_historical_candles(
            config,
            start=pd.Timestamp("2026-11-12T10:00:00Z"),
            end=pd.Timestamp("2026-11-12T10:01:00Z"),
            now=pd.Timestamp("2026-11-13T12:00:00Z"),
            api_key="test-key",
            session=session,
            outputsize=10,
        )

    snapshot = result["credit_snapshot"]

    assert snapshot.credits_used == 1
    assert snapshot.credits_left == 799
    assert snapshot.information_available is True


def test_missing_credit_headers():
    config = create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )

    response = Mock()
    response.raise_for_status.return_value = None
    response.headers = {}

    response.json.return_value = {
        "meta": {
            "symbol": "EUR/USD",
            "interval": "1min",
        },
        "values": [
            {
                "datetime": "2026-11-12 10:00:00",
                "open": "1.1000",
                "high": "1.1010",
                "low": "1.0990",
                "close": "1.1005",
            }
        ],
    }

    session = Mock()
    session.get.return_value = response

    with patch("market_data.historical_collector.reserve_request"):
        result = fetch_historical_candles(
            config,
            start=pd.Timestamp("2026-11-12T10:00:00Z"),
            end=pd.Timestamp("2026-11-12T10:01:00Z"),
            now=pd.Timestamp("2026-11-13T12:00:00Z"),
            api_key="test-key",
            session=session,
            outputsize=10,
        )

    assert result["credit_snapshot"].information_available is False
