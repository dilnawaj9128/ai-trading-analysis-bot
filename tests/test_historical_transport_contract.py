from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd

from config.market_config import create_research_config
from market_data.historical_collector import (
    _perform_historical_http_request,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_transport_returns_response_without_reserving_budget():
    config = create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )

    response = Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.headers = {
        "api-credits-left": "95",
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

    session = Mock()
    session.get.return_value = response

    with patch(
        "market_data.twelve_data_client.reserve_request"
    ) as reserve:
        payload, snapshot, original_response = (
            _perform_historical_http_request(
                config,
                start=pd.Timestamp(
                    "2026-11-12T10:00:00Z"
                ),
                end=pd.Timestamp(
                    "2026-11-12T10:01:00Z"
                ),
                step=pd.Timedelta(minutes=1),
                key="mock-key",
                outputsize=10,
                session=session,
                now=pd.Timestamp(NOW),
            )
        )

    reserve.assert_not_called()
    session.get.assert_called_once()

    assert original_response is response
    assert payload["meta"]["symbol"] == "EUR/USD"
    assert snapshot.credits_left == 95
