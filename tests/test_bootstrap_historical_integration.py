import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from config.market_config import create_research_config
from market_data.historical_collector import (
    fetch_bootstrap_historical_candles,
)
from market_data.bootstrap_request_coordinator import BootstrapNotPermitted


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def response():
    result = Mock()
    result.status_code = 200
    result.raise_for_status.return_value = None
    result.headers = {"api-credits-left": "99"}
    result.json.return_value = {
        "meta": {"symbol": "EUR/USD", "interval": "1min"},
        "values": [{
            "datetime": "2026-11-12 10:00:00",
            "open": "1.1000",
            "high": "1.1010",
            "low": "1.0990",
            "close": "1.1005",
        }],
    }
    return result


def execute(tmp_path, session, **overrides):
    args = {
        "start": "2026-11-12T10:00:00Z",
        "end": "2026-11-12T10:01:00Z",
        "approval_id": "test-approval",
        "explicitly_approved": True,
        "api_key": "mock-key",
        "state_path": tmp_path / "budget.json",
        "provider_credit_path": tmp_path / "provider.json",
        "approval_path": tmp_path / "approval.json",
        "now": NOW,
        "session": session,
        "outputsize": 10,
    }
    args.update(overrides)
    return fetch_bootstrap_historical_candles(config(), **args)


def test_bootstrap_fetches_and_validates_candles(tmp_path):
    session = Mock()
    session.get.return_value = response()

    result = execute(tmp_path, session)

    assert result["candles"] == 1
    assert result["analysis_only"] is True
    assert result["execution_enabled"] is False
    assert result["bootstrap"].credits_refreshed is True

    session.get.assert_called_once()

    budget = json.loads((tmp_path / "budget.json").read_text())
    assert budget["minute_used"] == 1
    assert budget["day_used"] == 1


def test_missing_approval_blocks_http(tmp_path):
    session = Mock()

    with pytest.raises(BootstrapNotPermitted):
        execute(tmp_path, session, explicitly_approved=False)

    session.get.assert_not_called()


def test_invalid_window_does_not_consume_approval(tmp_path):
    session = Mock()

    with pytest.raises(ValueError):
        execute(
            tmp_path,
            session,
            end="2026-11-14T10:01:00Z",
        )

    session.get.assert_not_called()
    assert not (tmp_path / "approval.json").exists()
    assert not (tmp_path / "budget.json").exists()


def test_second_bootstrap_blocked(tmp_path):
    session = Mock()
    session.get.return_value = response()

    execute(tmp_path, session)

    with pytest.raises(BootstrapNotPermitted):
        execute(tmp_path, session)

    session.get.assert_called_once()


def test_missing_headers_does_not_refresh_credits(tmp_path):
    session = Mock()
    result = response()
    result.headers = {}
    session.get.return_value = result

    output = execute(tmp_path, session)

    assert output["candles"] == 1
    assert output["bootstrap"].credits_refreshed is False
    assert not (tmp_path / "provider.json").exists()


def test_provider_json_error_rejected(tmp_path):
    from market_data.twelve_data_client import MarketDataError

    session = Mock()
    result = response()
    result.json.return_value = {
        "status": "error",
        "code": 400,
        "message": "Invalid API request",
    }
    session.get.return_value = result

    with pytest.raises(MarketDataError, match="Provider error"):
        execute(tmp_path, session)

    session.get.assert_called_once()
    assert (tmp_path / "approval.json").exists()


def test_invalid_ohlc_rejected(tmp_path):
    from market_data.twelve_data_client import MarketDataError

    session = Mock()
    result = response()
    result.json.return_value["values"][0]["high"] = "1.0000"
    session.get.return_value = result

    with pytest.raises(MarketDataError, match="Invalid OHLC"):
        execute(tmp_path, session)

    assert (tmp_path / "approval.json").exists()


def test_outside_window_candle_rejected(tmp_path):
    from market_data.twelve_data_client import MarketDataError

    session = Mock()
    result = response()
    result.json.return_value["values"][0]["datetime"] = (
        "2026-11-12 10:02:00"
    )
    session.get.return_value = result

    with pytest.raises(
        MarketDataError,
        match="outside requested window",
    ):
        execute(tmp_path, session)

    assert (tmp_path / "approval.json").exists()


def test_invalid_data_consumes_single_budget_reservation(tmp_path):
    import json
    from market_data.twelve_data_client import MarketDataError

    session = Mock()
    result = response()
    result.json.return_value["values"][0]["close"] = "-1"
    session.get.return_value = result

    with pytest.raises(MarketDataError):
        execute(tmp_path, session)

    budget = json.loads((tmp_path / "budget.json").read_text())

    assert budget["minute_used"] == 1
    assert budget["day_used"] == 1
    session.get.assert_called_once()


def test_missing_headers_block_next_guarded_request(tmp_path):
    from market_data.provider_credit_guard import (
        ProviderCreditStatusUnknown,
    )
    from market_data.historical_collector import (
        fetch_historical_candles,
    )

    session = Mock()
    result = response()
    result.headers = {}
    session.get.return_value = result

    execute(tmp_path, session)

    with pytest.raises(ProviderCreditStatusUnknown):
        fetch_historical_candles(
            config(),
            start="2026-11-12T10:00:00Z",
            end="2026-11-12T10:01:00Z",
            api_key="mock-key",
            state_path=tmp_path / "budget.json",
            provider_credit_path=tmp_path / "provider.json",
            now=NOW,
            session=session,
            outputsize=10,
        )

    session.get.assert_called_once()


def test_invalid_candles_do_not_refresh_provider_credits(tmp_path):
    from market_data.twelve_data_client import MarketDataError

    session = Mock()
    result = response()
    result.json.return_value["values"][0]["close"] = "-1"
    session.get.return_value = result

    with pytest.raises(MarketDataError):
        execute(tmp_path, session)

    assert not (tmp_path / "provider.json").exists()
    assert (tmp_path / "approval.json").exists()

    budget = json.loads((tmp_path / "budget.json").read_text())
    assert budget["minute_used"] == 1


def test_provider_error_does_not_refresh_provider_credits(tmp_path):
    from market_data.twelve_data_client import MarketDataError

    session = Mock()
    result = response()
    result.json.return_value = {
        "status": "error",
        "code": 400,
        "message": "Invalid request",
    }
    session.get.return_value = result

    with pytest.raises(MarketDataError):
        execute(tmp_path, session)

    assert not (tmp_path / "provider.json").exists()
    assert (tmp_path / "approval.json").exists()


def test_valid_candles_still_refresh_provider_credits(tmp_path):
    from market_data.provider_credit_state import load_credit_state

    session = Mock()
    session.get.return_value = response()

    output = execute(tmp_path, session)

    assert output["candles"] == 1
    assert output["bootstrap"].credits_refreshed is True

    snapshot = load_credit_state(
        path=tmp_path / "provider.json",
        now=NOW,
    )
    assert snapshot.credits_left == 99
