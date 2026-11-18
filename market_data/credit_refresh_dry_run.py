"""Integrated credit-refresh dry run.

Simulation only: never uses a real HTTP transport or production state.
"""

from pathlib import Path
from types import SimpleNamespace

from market_data.twelve_data_client import reserve_request
from market_data.credit_response_handler import (
    refresh_credits_from_response,
)
from market_data.provider_credit_state import load_credit_state


def execute_refresh_dry_run(
    *,
    workspace,
    explicitly_approved=False,
    simulate_failure=False,
):
    if explicitly_approved is not True:
        return {
            "status": "BLOCKED",
            "reason": "Explicit approval required",
            "credits_left": None,
        }

    root = Path(workspace)

    # Never use production credit/budget paths.
    if root.resolve() == Path.cwd().resolve():
        raise ValueError("Project root cannot be dry-run workspace")

    if not root.exists() or not root.is_dir():
        raise ValueError("Existing isolated workspace required")

    provider = root / "dry_run_provider.json"
    budget = root / "dry_run_budget.json"

    # Reserve budget before the simulated response.
    reserve_request(path=budget)

    if simulate_failure:
        return {
            "status": "UNCERTAIN",
            "reason": "Simulated transport failure; no retry",
            "credits_left": None,
        }

    response = SimpleNamespace(
        status_code=200,
        headers={
            "api-credits-used": "1",
            "api-credits-left": "7",
        },
    )

    refresh = refresh_credits_from_response(
        response,
        path=provider,
    )

    if refresh.updated is not True:
        return {
            "status": "UNCERTAIN",
            "reason": "Credit snapshot update unsuccessful",
            "credits_left": None,
        }

    snapshot = load_credit_state(path=provider)

    if snapshot is None:
        return {
            "status": "UNCERTAIN",
            "reason": "Persisted snapshot unavailable",
            "credits_left": None,
        }

    return {
        "status": "SIMULATED_SNAPSHOT_READY",
        "credits_left": snapshot.credits_left,
        "real_http_executed": False,
        "settlement_authorized": False,
    }
