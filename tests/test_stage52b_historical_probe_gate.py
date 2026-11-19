"""Stage 52B: unresolved probe blocks historical acquisition."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from config.market_config import create_research_config
from market_data import probe_cross_path_gate as gate
from market_data.historical_collector import (
    fetch_historical_candles,
    fetch_bootstrap_historical_candles,
)

NOW = datetime.now(timezone.utc)


def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


@pytest.fixture
def uncertain_probe(tmp_path, monkeypatch):
    journal = tmp_path / "probe.json"
    journal.write_text(json.dumps({
        "version": 1,
        "attempts": [{
            "started_at": (
                NOW - timedelta(minutes=5)
            ).isoformat(),
            "status": "UNCERTAIN",
        }],
    }))
    monkeypatch.setattr(gate, "PROBE_STATE", journal)
    return journal


def test_standard_request_blocked_before_budget(
    tmp_path, uncertain_probe
):
    session = Mock()
    start = NOW - timedelta(days=1)
    start = start.replace(second=0, microsecond=0)

    with pytest.raises(gate.CrossPathProbeBlocked):
        fetch_historical_candles(
            config(),
            start=start,
            end=start + timedelta(minutes=2),
            api_key="FAKE_KEY",
            state_path=tmp_path / "budget.json",
            provider_credit_path=tmp_path / "credits.json",
            session=session,
        )

    session.get.assert_not_called()
    assert not (tmp_path / "budget.json").exists()


def test_bootstrap_blocked_before_approval(
    tmp_path, uncertain_probe
):
    session = Mock()
    start = NOW - timedelta(days=1)
    start = start.replace(second=0, microsecond=0)

    with pytest.raises(gate.CrossPathProbeBlocked):
        fetch_bootstrap_historical_candles(
            config(),
            start=start,
            end=start + timedelta(minutes=2),
            approval_id="offline-test",
            explicitly_approved=True,
            api_key="FAKE_KEY",
            approval_path=tmp_path / "approval.json",
            state_path=tmp_path / "budget.json",
            provider_credit_path=tmp_path / "credits.json",
            session=session,
        )

    session.get.assert_not_called()
    assert not (tmp_path / "approval.json").exists()
    assert not (tmp_path / "budget.json").exists()


def test_transport_itself_cannot_bypass_gate(
    tmp_path, uncertain_probe
):
    from market_data.historical_collector import (
        _perform_historical_http_request,
    )

    session = Mock()
    start = NOW - timedelta(days=1)
    start = start.replace(second=0, microsecond=0)

    with pytest.raises(gate.CrossPathProbeBlocked):
        _perform_historical_http_request(
            config(),
            start=start,
            end=start + timedelta(minutes=2),
            step=timedelta(minutes=1),
            key="FAKE_KEY",
            outputsize=10,
            session=session,
        )

    session.get.assert_not_called()
