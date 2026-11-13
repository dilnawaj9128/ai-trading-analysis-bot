from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from config.market_config import create_research_config
from market_data.historical_collector import fetch_historical_candles
from market_data.twelve_data_client import MarketDataError


def test_invalid_candle_marks_reservation_uncertain():
    config = create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )

    now = pd.Timestamp(
        datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    )

    invalid_payload = {
        "meta": {
            "symbol": "EUR/USD",
            "interval": "1min",
        },
        "values": [
            {
                "datetime": "2026-11-13 12:05:00",
                "open": "1.1000",
                "high": "1.1010",
                "low": "1.0990",
                "close": "1.1005",
            }
        ],
    }

    with (
        patch(
            "market_data.historical_collector._validate_historical_request"
        ) as validate,
        patch(
            "market_data.historical_collector.authorize_request"
        ) as authorize,
        patch(
            "market_data.historical_collector._perform_historical_http_request"
        ) as transport,
        patch(
            "market_data.authorization_ledger.transition_authorization"
        ) as transition,
    ):
        validate.return_value = (
            now - pd.Timedelta(minutes=10),
            now,
            now,
            pd.Timedelta(minutes=1),
            "fake-test-key",
        )

        authorize.return_value = SimpleNamespace(
            request_id="invalid-candle-request"
        )

        transport.return_value = (
            invalid_payload,
            None,
            SimpleNamespace(status_code=200, headers={}),
        )

        with pytest.raises(
            MarketDataError,
            match="Candle outside requested window",
        ):
            fetch_historical_candles(
                config,
                start=now - pd.Timedelta(minutes=10),
                end=now,
                api_key="fake-test-key",
                provider_credit_path="fake-provider.json",
            )

        transition.assert_called_once_with(
            provider_state_path="fake-provider.json",
            request_id="invalid-candle-request",
            status="UNCERTAIN",
        )
