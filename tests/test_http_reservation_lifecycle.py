from unittest.mock import patch

import pytest

from market_data.historical_collector import (
    fetch_historical_candles,
)
from market_data.twelve_data_client import MarketDataError
from config.market_config import create_research_config


@pytest.mark.parametrize(
    "failure",
    [
        MarketDataError("network error"),
        MarketDataError("HTTP 429"),
        MarketDataError("invalid JSON"),
    ],
)
def test_http_failure_marks_reservation_uncertain(failure):
    config = create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )

    with (
        patch(
            "market_data.historical_collector._validate_historical_request"
        ) as validate,
        patch(
            "market_data.historical_collector.authorize_request"
        ) as authorize,
        patch(
            "market_data.historical_collector._perform_historical_http_request",
            side_effect=failure,
        ),
        patch(
            "market_data.authorization_ledger.transition_authorization"
        ) as transition,
    ):
        from datetime import datetime, timezone
        import pandas as pd

        now = pd.Timestamp(
            datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        )

        validate.return_value = (
            now - pd.Timedelta(minutes=10),
            now,
            now,
            pd.Timedelta(minutes=1),
            "fake-test-key",
        )

        authorize.return_value.request_id = "test-request-123"

        with pytest.raises(MarketDataError):
            fetch_historical_candles(
                config,
                start=now - pd.Timedelta(minutes=10),
                end=now,
                api_key="fake-test-key",
                provider_credit_path="fake-provider.json",
            )

        transition.assert_called_once_with(
            provider_state_path="fake-provider.json",
            request_id="test-request-123",
            status="UNCERTAIN",
        )
