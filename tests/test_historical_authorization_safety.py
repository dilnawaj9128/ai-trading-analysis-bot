"""Offline tests: historical HTTP must require valid authorization."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.market_config import create_research_config
from market_data.historical_collector import fetch_historical_candles
from market_data.provider_credit_guard import ProviderCreditStatusUnknown
from market_data.twelve_data_client import MarketDataError


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
START = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 12, 10, 3, tzinfo=timezone.utc)


def config():
    return create_research_config(
        platform="quotex",
        market="forex",
        symbol="EUR/USD",
        timeframe="1min",
        expiry_minutes=15,
    )


def test_default_path_must_check_provider_credits(tmp_path):
    with (
        patch(
            "market_data.historical_collector.authorize_request",
            side_effect=ProviderCreditStatusUnknown(
                "Provider credit status unknown"
            ),
        ) as authorization,
        patch(
            "market_data.historical_collector._perform_historical_http_request",
            side_effect=AssertionError("HTTP must not execute"),
        ) as transport,
    ):
        with pytest.raises(ProviderCreditStatusUnknown):
            fetch_historical_candles(
                config(),
                start=START,
                end=END,
                now=NOW,
                api_key="offline-test-key",
                state_path=tmp_path / "local_budget.json",
            )

        authorization.assert_called_once()
        transport.assert_not_called()


def test_incomplete_authorization_blocks_http(tmp_path):
    incomplete = SimpleNamespace(
        authorized=False,
        local_budget_reserved=False,
        request_id="",
    )

    with (
        patch(
            "market_data.historical_collector.authorize_request",
            return_value=incomplete,
        ),
        patch(
            "market_data.historical_collector._perform_historical_http_request",
            side_effect=AssertionError("HTTP must not execute"),
        ) as transport,
    ):
        with pytest.raises(MarketDataError, match="Incomplete"):
            fetch_historical_candles(
                config(),
                start=START,
                end=END,
                now=NOW,
                api_key="offline-test-key",
                state_path=tmp_path / "local_budget.json",
                provider_credit_path=tmp_path / "provider_credits.json",
            )

        transport.assert_not_called()
