from unittest.mock import Mock, patch

import pytest

from market_data.api_retry import fetch_with_retry
from market_data.twelve_data_client import (
    BudgetExceeded,
    MarketDataError,
)


def test_success_without_retry():
    fetcher = Mock(return_value={"candles": 100})

    result = fetch_with_retry(fetcher)

    assert result["candles"] == 100
    assert fetcher.call_count == 1


def test_minute_budget_retry():
    fetcher = Mock(
        side_effect=[
            BudgetExceeded("Local minute budget exhausted"),
            {"candles": 100},
        ]
    )

    with patch("market_data.api_retry.time.sleep") as sleep:
        result = fetch_with_retry(
            fetcher,
            max_attempts=3,
            wait_seconds=65,
        )

    assert result["candles"] == 100
    assert fetcher.call_count == 2
    sleep.assert_called_once_with(65)


def test_daily_budget_not_retried():
    fetcher = Mock(
        side_effect=BudgetExceeded("Local daily budget exhausted")
    )

    with patch("market_data.api_retry.time.sleep") as sleep:
        with pytest.raises(BudgetExceeded, match="daily"):
            fetch_with_retry(fetcher)

    assert fetcher.call_count == 1
    sleep.assert_not_called()


def test_provider_error_not_retried():
    fetcher = Mock(
        side_effect=MarketDataError("Provider rejected request")
    )

    with patch("market_data.api_retry.time.sleep") as sleep:
        with pytest.raises(MarketDataError):
            fetch_with_retry(fetcher)

    assert fetcher.call_count == 1
    sleep.assert_not_called()


def test_retry_attempts_exhausted():
    fetcher = Mock(
        side_effect=BudgetExceeded("Local minute budget exhausted")
    )

    with patch("market_data.api_retry.time.sleep") as sleep:
        with pytest.raises(BudgetExceeded):
            fetch_with_retry(
                fetcher,
                max_attempts=3,
                wait_seconds=65,
            )

    assert fetcher.call_count == 3
    assert sleep.call_count == 2
