"""Offline integration tests for authorized live research fetching."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.market_config import create_research_config
from market_data import authorized_live_fetch as live
from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def research_config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def provider_snapshot(path):
    """Synthetic provider evidence, isolated to pytest tmp_path."""
    snapshot = CreditSnapshot(
        credits_used=10,
        credits_left=100,
        low_credits=False,
        information_available=True,
    )
    save_credit_state(snapshot, path=path, now=NOW)


def fake_payload():
    return {
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


class FakeSession:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def get(self, *args, **kwargs):
        self.calls += 1

        if self.fail:
            raise ConnectionError("Simulated network failure")

        return SimpleNamespace(
            headers={},
            raise_for_status=lambda: None,
            json=fake_payload,
        )


def ledger_path(provider_path):
    return provider_path.with_name(
        provider_path.name + ".reservations.json"
    )


def test_success_reserves_exactly_one_local_request(tmp_path):
    provider = tmp_path / "provider_credits.json"
    budget = tmp_path / "local_budget.json"
    provider_snapshot(provider)

    session = FakeSession()

    with patch.object(live, "refresh_credits_from_response", return_value=type("Refresh", (), {"updated": True})()):
        result = live.fetch_authorized_live_candles(
            research_config(),
            api_key="fake-key",
            provider_credit_path=provider,
            state_path=budget,
            now=NOW,
            session=session,
        )

    assert session.calls == 1
    assert result["candles"] == 1
    assert result["analysis_only"] is True
    assert result["execution_enabled"] is False

    usage = json.loads(budget.read_text())
    assert usage["day_used"] == 1
    assert usage["minute_used"] == 1

    ledger = json.loads(ledger_path(provider).read_text())
    assert ledger["reserved"] == 1
    assert len(ledger["requests"]) == 1

    entry = next(iter(ledger["requests"].values()))
    assert entry["credits"] == 1
    assert entry["status"] == "PENDING"


def test_failed_http_preserves_uncertain_reservation(tmp_path):
    provider = tmp_path / "provider_credits.json"
    budget = tmp_path / "local_budget.json"
    provider_snapshot(provider)

    session = FakeSession(fail=True)

    with pytest.raises(live.td.MarketDataError):
        live.fetch_authorized_live_candles(
            research_config(),
            api_key="fake-key",
            provider_credit_path=provider,
            state_path=budget,
            now=NOW,
            session=session,
        )

    assert session.calls == 1

    usage = json.loads(budget.read_text())
    assert usage["day_used"] == 1

    ledger = json.loads(ledger_path(provider).read_text())
    assert ledger["reserved"] == 1

    entry = next(iter(ledger["requests"].values()))
    assert entry["status"] == "UNCERTAIN"


def test_missing_provider_snapshot_blocks_http(tmp_path):
    provider = tmp_path / "provider_credits.json"
    budget = tmp_path / "local_budget.json"

    session = FakeSession()

    with pytest.raises(Exception):
        live.fetch_authorized_live_candles(
            research_config(),
            api_key="fake-key",
            provider_credit_path=provider,
            state_path=budget,
            now=NOW,
            session=session,
        )

    assert session.calls == 0
    assert not budget.exists()
    assert not ledger_path(provider).exists()


def test_second_request_preserves_existing_reservations(tmp_path):
    provider = tmp_path / "provider_credits.json"
    budget = tmp_path / "local_budget.json"
    provider_snapshot(provider)

    session = FakeSession()

    with patch.object(live, "refresh_credits_from_response", return_value=type("Refresh", (), {"updated": True})()):
        for _ in range(2):
            live.fetch_authorized_live_candles(
                research_config(),
                api_key="fake-key",
                provider_credit_path=provider,
                state_path=budget,
                now=NOW,
                session=session,
            )

    assert session.calls == 2

    usage = json.loads(budget.read_text())
    assert usage["day_used"] == 2
    assert usage["minute_used"] == 2

    ledger = json.loads(ledger_path(provider).read_text())
    assert ledger["reserved"] == 2
    assert len(ledger["requests"]) == 2

    assert all(
        entry["status"] == "PENDING"
        for entry in ledger["requests"].values()
    )
