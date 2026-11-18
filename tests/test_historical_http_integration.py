from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from config.market_config import create_research_config
from market_data.historical_collector import fetch_historical_candles
from market_data.twelve_data_client import MarketDataError


START = pd.Timestamp("2026-11-12T10:00:00Z")
END = pd.Timestamp("2026-11-12T10:02:00Z")
NOW = pd.Timestamp("2026-11-13T12:00:00Z")


@pytest.fixture
def config():
    return create_research_config(
        "quotex",
        "forex",
        "EUR/USD",
        "1min",
        15,
    )


def run_fetch(config, response):
    session = Mock()
    session.get.return_value = response

    with patch(
        "market_data.historical_collector.reserve_request"
    ) as reserve:
        try:
            result = fetch_historical_candles(
                config,
                start=START,
                end=END,
                now=NOW,
                api_key="test-key",
                session=session,
                outputsize=10,
            )
            return result, session, reserve
        except Exception:
            raise


@pytest.mark.parametrize("status_code", [429, 500])
def test_http_errors_are_rejected(config, status_code):
    response = Mock()

    response.raise_for_status.side_effect = requests.HTTPError(
        f"HTTP {status_code}",
        response=response,
    )

    response.status_code = status_code

    with pytest.raises(
        MarketDataError,
        match="Historical request failed",
    ):
        run_fetch(config, response)


def test_valid_http_response(config, mock_historical_authorization):
    response = Mock()
    response.headers = {"api-credits-used": "1", "api-credits-left": "7"}
    response.raise_for_status.return_value = None

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
            },
            {
                "datetime": "2026-11-12 10:01:00",
                "open": "1.1005",
                "high": "1.1020",
                "low": "1.1000",
                "close": "1.1015",
            },
        ],
    }

    result, session, reserve = run_fetch(config, response)

    assert result["candles"] == 2
    assert result["possibly_truncated"] is False
    assert result["analysis_only"] is True
    assert result["execution_enabled"] is False

    mock_historical_authorization.assert_called_once()
    session.get.assert_called_once()


def test_provider_error_payload(config):
    response = Mock()
    response.headers = {}
    response.raise_for_status.return_value = None

    response.json.return_value = {
        "status": "error",
        "code": 429,
        "message": "API credits exhausted",
    }

    with pytest.raises(
        MarketDataError,
        match="Provider error",
    ):
        run_fetch(config, response)


@pytest.fixture(autouse=True)
def mock_historical_authorization():
    """Simulate successful authorization; never touch real quota files."""
    from types import SimpleNamespace

    approval = SimpleNamespace(
        authorized=True,
        local_budget_reserved=True,
        request_id="offline-authorized-request",
    )

    with (
        patch(
            "market_data.historical_collector.authorize_request",
            return_value=approval,
        ) as authorization,
        patch(
            "market_data.historical_collector.refresh_credits_from_response",
            side_effect=lambda response, **kwargs: SimpleNamespace(
                updated=response.headers.get("api-credits-left") is not None
            ),
        ),
        patch(
            "market_data.authorization_ledger.transition_authorization"
        ),
    ):
        yield authorization
