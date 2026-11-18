"""Regression tests for manual refresh production-path safety."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from market_data.manual_credit_refresh import (
    ManualRefreshBlocked,
    manual_credit_refresh,
)
from market_data.twelve_data_client import STATE_PATH


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def attempt(provider, budget):
    called = []

    def callback():
        called.append(True)
        raise AssertionError("Callback must not execute")

    with pytest.raises(
        ManualRefreshBlocked,
        match="Production refresh authorization not implemented",
    ):
        manual_credit_refresh(
            request_callback=callback,
            approval_id="stage22d-test",
            explicitly_approved=True,
            provider_path=provider,
            budget_path=budget,
            now=NOW,
        )

    assert called == []


def test_default_production_provider_blocked(tmp_path):
    attempt(
        Path("data/api_usage/provider_credits.json"),
        tmp_path / "budget.json",
    )


def test_alternative_production_filename_blocked(tmp_path):
    attempt(
        Path("data/api_usage/alternative_provider.json"),
        tmp_path / "budget.json",
    )


def test_production_budget_path_blocked(tmp_path):
    attempt(
        tmp_path / "provider.json",
        STATE_PATH,
    )


def test_symlink_to_production_directory_blocked(tmp_path):
    alias = tmp_path / "production_alias"
    alias.symlink_to(Path("data/api_usage").resolve(), target_is_directory=True)

    attempt(
        alias / "alternative_provider.json",
        tmp_path / "budget.json",
    )
