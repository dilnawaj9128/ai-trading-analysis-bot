from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from config.market_config import create_research_config
from market_data.historical_collector import fetch_historical_candles
from market_data.twelve_data_client import MarketDataError


@pytest.fixture
def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def execute(config, response):
    session = Mock()
    session.get.return_value = response

    with patch("market_data.historical_collector.reserve_request"):
        return fetch_historical_candles(
            config,
            start=pd.Timestamp("2026-11-12T10:00:00Z"),
            end=pd.Timestamp("2026-11-12T10:02:00Z"),
            now=pd.Timestamp("2026-11-13T12:00:00Z"),
            api_key="test-key",
            session=session,
            outputsize=10,
        )


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, "HTTP 429 rate limit exceeded"),
        (500, "HTTP 500 provider server error"),
        (503, "HTTP 503 provider server error"),
        (403, "HTTP 403"),
    ],
)
def test_http_status_classification(config, status, expected):
    response = Mock()
    response.status_code = status
    response.raise_for_status.side_effect = requests.HTTPError(
        f"HTTP {status}",
        response=response,
    )

    with pytest.raises(MarketDataError, match=expected):
        execute(config, response)


def test_invalid_json_classification(config):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("Invalid JSON")

    with pytest.raises(MarketDataError, match="invalid JSON"):
        execute(config, response)


def test_network_error_classification(config):
    session = Mock()
    session.get.side_effect = requests.ConnectionError(
        "Connection refused"
    )

    with patch("market_data.historical_collector.reserve_request"):
        with pytest.raises(MarketDataError, match="network error"):
            fetch_historical_candles(
                config,
                start=pd.Timestamp("2026-11-12T10:00:00Z"),
                end=pd.Timestamp("2026-11-12T10:02:00Z"),
                now=pd.Timestamp("2026-11-13T12:00:00Z"),
                api_key="test-key",
                session=session,
                outputsize=10,
            )
