"""Stage 52C: legacy live route requires unified authorization."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from config.market_config import create_research_config
from market_data import twelve_data_client as td
from market_data import probe_cross_path_gate as gate

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


@pytest.fixture(autouse=True)
def isolate_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gate,
        "PROBE_STATE",
        tmp_path / "probe.json",
    )


def test_denied_credit_authorization_never_uses_http(tmp_path):
    session = Mock()

    with patch(
        "market_data.authorized_live_fetch.authorize_request",
        side_effect=ValueError("Provider credits unavailable"),
    ) as authorize:
        with pytest.raises(ValueError, match="Provider credits"):
            td.fetch_recent_candles(
                config(),
                api_key="FAKE_KEY",
                state_path=tmp_path / "budget.json",
                now=NOW,
                session=session,
            )

    authorize.assert_called_once()
    session.get.assert_not_called()
    assert not (tmp_path / "budget.json").exists()


def test_legacy_route_no_longer_reserves_directly(tmp_path):
    session = Mock()

    with (
        patch.object(
            td,
            "reserve_request",
            side_effect=AssertionError(
                "Legacy budget-only reservation must not run"
            ),
        ) as legacy_reserve,
        patch(
            "market_data.authorized_live_fetch.authorize_request",
            side_effect=ValueError("Authorization denied"),
        ),
    ):
        with pytest.raises(ValueError, match="Authorization denied"):
            td.fetch_recent_candles(
                config(),
                api_key="FAKE_KEY",
                state_path=tmp_path / "budget.json",
                now=NOW,
                session=session,
            )

    legacy_reserve.assert_not_called()
    session.get.assert_not_called()
