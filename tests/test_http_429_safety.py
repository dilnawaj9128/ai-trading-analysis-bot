from unittest.mock import Mock, patch

import pytest
import requests

from market_data.api_retry import fetch_with_retry


def test_http_429_not_retried_automatically():
    calls = []

    def fake_fetch():
        calls.append(1)

        response = Mock()
        response.status_code = 429

        raise requests.HTTPError(
            "429 Too Many Requests",
            response=response,
        )

    with patch("market_data.api_retry.time.sleep") as sleep:
        with pytest.raises(requests.HTTPError):
            fetch_with_retry(
                fake_fetch,
                max_attempts=3,
                wait_seconds=65,
            )

    assert len(calls) == 1
    sleep.assert_not_called()


def test_provider_error_not_retried():
    calls = []

    def fake_fetch():
        calls.append(1)
        raise RuntimeError("Provider unavailable")

    with pytest.raises(RuntimeError):
        fetch_with_retry(
            fake_fetch,
            max_attempts=3,
            wait_seconds=0,
        )

    assert len(calls) == 1
