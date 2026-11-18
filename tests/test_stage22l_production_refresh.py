import json

import pytest

import market_data.manual_credit_refresh as refresh_module
from market_data.manual_credit_refresh import (
    ManualRefreshBlocked,
    refresh_production_provider_credits,
)


def paths(tmp_path):
    return {
        "provider_path": tmp_path / "provider.json",
        "budget_path": tmp_path / "budget.json",
        "approval_path": tmp_path / "approval.json",
        "lifecycle_path": tmp_path / "lifecycle.json",
        "execution_path": tmp_path / "execution.json",
    }


def test_requires_explicit_approval(tmp_path):
    with pytest.raises(
        ManualRefreshBlocked,
        match="Explicit approval",
    ):
        refresh_production_provider_credits(
            approval_id="test-approval",
            api_key="fake-test-key",
            **paths(tmp_path),
        )


def test_failed_http_request_cannot_retry(tmp_path, monkeypatch):
    import requests

    calls = []

    def failing_get(*args, **kwargs):
        calls.append(True)
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(requests, "get", failing_get)

    arguments = paths(tmp_path)

    result = refresh_production_provider_credits(
        approval_id="test-approval",
        explicitly_approved=True,
        api_key="fake-test-key",
        **arguments,
    )

    assert result["status"] == "UNCERTAIN"
    assert result["retry_allowed"] is False
    assert len(calls) == 1

    execution = json.loads(
        arguments["execution_path"].read_text()
    )
    assert execution["status"] == "UNCERTAIN"

    with pytest.raises(Exception):
        refresh_production_provider_credits(
            approval_id="test-approval",
            explicitly_approved=True,
            api_key="fake-test-key",
            **arguments,
        )

    assert len(calls) == 1
