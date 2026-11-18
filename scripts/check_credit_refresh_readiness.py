"""Read-only credit refresh readiness check."""

import json
from datetime import datetime, timezone
from pathlib import Path

from market_data.credit_dashboard_status import (
    get_credit_dashboard_status,
)
from market_data.credit_refresh_policy import (
    decide_credit_refresh,
)
from market_data.provider_credit_state import DEFAULT_PATH
from market_data.unified_request_guard import journal_path_for


def main():
    provider = Path(DEFAULT_PATH)
    base = provider.parent
    claim = base / "bootstrap_claim.json"

    recovery = provider.with_name(
        provider.name + ".recovery_required.json"
    )

    journal = journal_path_for(provider)
    ledger = provider.with_name(
        provider.name + ".reservations.json"
    )

    credit = get_credit_dashboard_status()

    print("=== STAGE 20R: CREDIT REFRESH READINESS ===")
    print("Provider:", credit["status"])
    print("Bootstrap claim exists:", claim.exists())
    print("Journal exists:", journal.exists())
    print("Ledger exists:", ledger.exists())
    print("Recovery marker exists:", recovery.exists())

    # Conservative: an absent recovery marker is not proof
    # that the authorization state is fully reconciled.
    recovery_clear = (
        not recovery.exists()
        and journal.exists()
        and ledger.exists()
    )

    # This diagnostic does not independently validate local
    # budget availability or cooldown.
    decision = decide_credit_refresh(
        snapshot_status=credit["status"],
        explicitly_approved=False,
        local_budget_available=False,
        cooldown_satisfied=False,
        recovery_required=not recovery_clear,
    )

    print("Refresh decision:", decision.action)
    print("Reason:", decision.reason)
    print("Approval required:", decision.requires_approval)

    print("No network requests.")
    print("No approval claimed.")
    print("No state modified.")


if __name__ == "__main__":
    main()
