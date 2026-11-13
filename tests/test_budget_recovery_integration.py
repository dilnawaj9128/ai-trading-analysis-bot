import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.provider_credit_guard import ProviderCreditStatusUnknown
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_state(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    marker = tmp_path / "provider.json.recovery_required.json"
    ledger = tmp_path / "provider.json.reservations.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    return provider, budget, marker, ledger


def fail_budget_directory_sync(budget):
    """Fail only the budget directory fsync after replacement."""
    real_fsync = os.fsync
    real_replace = os.replace
    budget_replaced = False

    def tracking_replace(src, dst):
        nonlocal budget_replaced

        result = real_replace(src, dst)

        if os.fspath(dst) == os.fspath(budget):
            budget_replaced = True

        return result

    def tracking_fsync(fd):
        if (
            budget_replaced
            and os.path.isdir(f"/proc/self/fd/{fd}")
        ):
            raise OSError("Simulated budget directory sync failure")

        return real_fsync(fd)

    return tracking_replace, tracking_fsync


def test_budget_sync_failure_preserves_marker(tmp_path):
    provider, budget, marker, ledger = setup_state(tmp_path)

    tracking_replace, tracking_fsync = (
        fail_budget_directory_sync(budget)
    )

    with (
        patch(
            "market_data.twelve_data_client.os.replace",
            side_effect=tracking_replace,
        ),
        patch(
            "market_data.twelve_data_client.os.fsync",
            side_effect=tracking_fsync,
        ),
    ):
        with pytest.raises(
            OSError,
            match="Simulated budget directory sync failure",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert marker.exists()
    assert budget.exists()
    assert not ledger.exists()


def test_recovery_marker_blocks_second_reservation(tmp_path):
    provider, budget, marker, ledger = setup_state(tmp_path)

    tracking_replace, tracking_fsync = (
        fail_budget_directory_sync(budget)
    )

    with (
        patch(
            "market_data.twelve_data_client.os.replace",
            side_effect=tracking_replace,
        ),
        patch(
            "market_data.twelve_data_client.os.fsync",
            side_effect=tracking_fsync,
        ),
    ):
        with pytest.raises(OSError):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    before = budget.read_bytes()

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(
            ProviderCreditStatusUnknown,
            match="recovery",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert budget.read_bytes() == before
    assert marker.exists()


def test_uncertain_budget_commit_preserves_request_id(tmp_path):
    provider, budget, marker, ledger = setup_state(tmp_path)

    tracking_replace, tracking_fsync = (
        fail_budget_directory_sync(budget)
    )

    with (
        patch(
            "market_data.twelve_data_client.os.replace",
            side_effect=tracking_replace,
        ),
        patch(
            "market_data.twelve_data_client.os.fsync",
            side_effect=tracking_fsync,
        ),
    ):
        with pytest.raises(OSError):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    marker_state = json.loads(marker.read_text())
    budget_state = json.loads(budget.read_text())

    assert marker_state["recovery_required"] is True
    assert marker_state["reason"] == "authorization_commit_uncertain"
    assert isinstance(marker_state["request_id"], str)
    assert len(marker_state["request_id"]) == 32
    assert marker_state["credits"] == 1

    assert budget_state["minute_used"] == 1
    assert budget_state["day_used"] == 1

    assert not ledger.exists()
