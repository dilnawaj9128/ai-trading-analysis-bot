from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.market_config import create_research_config
from market_data import authorized_live_fetch as live


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def test_denied_authorization_never_calls_http():
    with (
        patch.object(
            live,
            "authorize_request",
            side_effect=ValueError("Provider credits unavailable"),
        ),
        patch.object(live.requests, "get") as http,
    ):
        with pytest.raises(ValueError, match="Provider credits"):
            live.fetch_authorized_live_candles(
                config(), api_key="fake-key", now=NOW
            )

        http.assert_not_called()


def test_successful_request_uses_one_authorization():
    payload = {
        "status": "ok",
        "meta": {"symbol": "EUR/USD", "interval": "1min"},
        "values": [{
            "datetime": "2026-11-18 11:59:00",
            "open": "1.1000",
            "high": "1.1010",
            "low": "1.0990",
            "close": "1.1005",
        }],
    }

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: payload,
        headers={},
    )

    session = SimpleNamespace(get=lambda *args, **kwargs: response)

    authorization = SimpleNamespace(
        authorized=True,
        local_budget_reserved=True,
        request_id="test-request-1",
    )

    with (
        patch.object(
            live, "authorize_request", return_value=authorization
        ) as authorize,
        patch.object(live, "refresh_credits_from_response", return_value=type("Refresh", (), {"updated": True})()),
        patch.object(
            live.td, "reserve_request"
        ) as reserve,
        patch.object(
            live, "transition_authorization"
        ) as transition,
    ):
        result = live.fetch_authorized_live_candles(
            config(),
            api_key="fake-key",
            now=NOW,
            session=session,
        )

        assert result["candles"] == 1
        assert result["analysis_only"] is True
        assert result["execution_enabled"] is False

        authorize.assert_called_once()
        reserve.assert_not_called()
        transition.assert_not_called()


def test_http_failure_marks_request_uncertain():
    class FailedSession:
        def get(self, *args, **kwargs):
            raise ConnectionError("Network unavailable")

    authorization = SimpleNamespace(
        authorized=True,
        local_budget_reserved=True,
        request_id="test-request-2",
    )

    with (
        patch.object(
            live, "authorize_request", return_value=authorization
        ),
        patch.object(
            live, "transition_authorization"
        ) as transition,
    ):
        with pytest.raises(live.td.MarketDataError):
            live.fetch_authorized_live_candles(
                config(),
                api_key="fake-key",
                now=NOW,
                session=FailedSession(),
            )

        transition.assert_called_once_with(
            provider_state_path=live.DEFAULT_PATH,
            request_id="test-request-2",
            status="UNCERTAIN",
        )


def test_incomplete_authorization_blocks_http():
    authorization = SimpleNamespace(
        authorized=False,
        local_budget_reserved=False,
        request_id="",
    )

    with (
        patch.object(
            live, "authorize_request", return_value=authorization
        ),
        patch.object(live.requests, "get") as http,
    ):
        with pytest.raises(
            live.td.MarketDataError,
            match="Incomplete request authorization",
        ):
            live.fetch_authorized_live_candles(
                config(), api_key="fake-key", now=NOW
            )

        http.assert_not_called()


def test_invalid_json_marks_uncertain():
    class Response:
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("Invalid JSON")

    authorization = SimpleNamespace(
        authorized=True,
        local_budget_reserved=True,
        request_id="invalid-json",
    )

    with (
        patch.object(
            live, "authorize_request", return_value=authorization
        ),
        patch.object(
            live, "transition_authorization"
        ) as transition,
    ):
        with pytest.raises(live.td.MarketDataError):
            live.fetch_authorized_live_candles(
                config(),
                api_key="fake-key",
                now=NOW,
                session=SimpleNamespace(
                    get=lambda *args, **kwargs: Response()
                ),
            )

        transition.assert_called_once()


def test_invalid_candles_mark_uncertain():
    class Response:
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "status": "ok",
                "meta": {
                    "symbol": "EUR/USD",
                    "interval": "1min",
                },
                "values": [],
            }

    authorization = SimpleNamespace(
        authorized=True,
        local_budget_reserved=True,
        request_id="invalid-candles",
    )

    with (
        patch.object(
            live, "authorize_request", return_value=authorization
        ),
        patch.object(
            live, "transition_authorization"
        ) as transition,
    ):
        with pytest.raises(live.td.MarketDataError):
            live.fetch_authorized_live_candles(
                config(),
                api_key="fake-key",
                now=NOW,
                session=SimpleNamespace(
                    get=lambda *args, **kwargs: Response()
                ),
            )

        transition.assert_called_once()


def test_credit_refresh_failure_marks_uncertain():
    authorization = SimpleNamespace(
        authorized=True,
        local_budget_reserved=True,
        request_id="refresh-failure",
    )

    payload = {
        "status": "ok",
        "meta": {
            "symbol": "EUR/USD",
            "interval": "1min",
        },
        "values": [{
            "datetime": "2026-11-18 11:59:00",
            "open": "1.1000",
            "high": "1.1010",
            "low": "1.0990",
            "close": "1.1005",
        }],
    }

    response = SimpleNamespace(
        headers={},
        raise_for_status=lambda: None,
        json=lambda: payload,
    )

    with (
        patch.object(
            live, "authorize_request", return_value=authorization
        ),
        patch.object(
            live,
            "refresh_credits_from_response",
            side_effect=ValueError("Invalid credit state"),
        ),
        patch.object(
            live, "transition_authorization"
        ) as transition,
    ):
        with pytest.raises(live.td.MarketDataError):
            live.fetch_authorized_live_candles(
                config(),
                api_key="fake-key",
                now=NOW,
                session=SimpleNamespace(
                    get=lambda *args, **kwargs: response
                ),
            )

        transition.assert_called_once()
