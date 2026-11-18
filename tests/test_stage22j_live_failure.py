from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import market_data.authorized_live_fetch as live


def test_network_and_ledger_failures_remain_blocked(monkeypatch):
    config = SimpleNamespace(
        platform="research",
        market="forex",
        symbol="EUR/USD",
        timeframe="1min",
        expiry_minutes=15,
    )

    monkeypatch.setattr(
        live,
        "create_research_config",
        lambda *args: config,
    )

    monkeypatch.setattr(
        live,
        "authorize_request",
        lambda **kwargs: SimpleNamespace(
            authorized=True,
            local_budget_reserved=True,
            request_id="test-request",
        ),
    )

    def failing_transition(**kwargs):
        raise RuntimeError("simulated ledger failure")

    monkeypatch.setattr(
        live,
        "transition_authorization",
        failing_transition,
    )

    class FailingSession:
        def get(self, *args, **kwargs):
            raise RuntimeError("simulated network failure")

    with pytest.raises(
        live.td.MarketDataError,
        match="manual review required",
    ) as result:
        live.fetch_authorized_live_candles(
            config,
            api_key="test-only-key",
            state_path="unused-test-budget.json",
            provider_credit_path="unused-test-provider.json",
            now=datetime(
                2026, 11, 18, 12, 0,
                tzinfo=timezone.utc,
            ),
            session=FailingSession(),
        )

    assert isinstance(result.value.__cause__, RuntimeError)
    assert "ledger failure" in str(result.value.__cause__)
