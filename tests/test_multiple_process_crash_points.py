import json
import subprocess
import sys
import textwrap
from datetime import datetime, timezone

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.authorization_journal import (
    AuthorizationJournalError,
    load_journal,
)
from market_data.provider_credit_guard import ProviderCreditStatusUnknown
from market_data.provider_credit_state import save_credit_state
from market_data.recovery_inspector import inspect_recovery_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

CASES = [
    ("_create_recovery_marker", "INCONSISTENT", "INTENT", False, False),
    ("reserve_request", "INCONSISTENT", "INTENT", True, False),
    ("finalize_intent", "COMMITTED", "INTENT", True, True),
    ("_clear_recovery_marker", "COMMITTED", "FINALIZED", True, True),
]


@pytest.mark.parametrize(
    "crash_point,expected_state,expected_journal,marker_exists,ledger_exists",
    CASES,
)
def test_process_crash_points_fail_closed(
    tmp_path,
    crash_point,
    expected_state,
    expected_journal,
    marker_exists,
    ledger_exists,
):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    child_code = textwrap.dedent("""
        import os
        import sys
        from datetime import datetime, timezone
        from unittest.mock import patch

        from market_data.unified_request_guard import authorize_request

        provider = sys.argv[1]
        budget = sys.argv[2]
        crash_point = sys.argv[3]

        def terminate(*args, **kwargs):
            os._exit(77)

        with patch(
            "market_data.unified_request_guard." + crash_point,
            side_effect=terminate,
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=datetime(
                    2026, 11, 13, 12, 0,
                    tzinfo=timezone.utc,
                ),
            )
    """)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            child_code,
            str(provider),
            str(budget),
            crash_point,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 77, (
        result.stdout + result.stderr
    )

    marker_path = tmp_path / "provider.json.recovery_required.json"
    ledger_path = tmp_path / "provider.json.reservations.json"
    journal_path = tmp_path / "provider.json.authorization_journal.json"

    assert marker_path.exists() is marker_exists
    assert ledger_path.exists() is ledger_exists
    assert journal_path.exists()

    journal = load_journal(journal_path)
    assert len(journal["transactions"]) == 1

    request_id, transaction = next(
        iter(journal["transactions"].items())
    )

    assert transaction["status"] == expected_journal

    if marker_exists:
        marker = json.loads(marker_path.read_text())
        assert marker["request_id"] == request_id

    if ledger_exists:
        ledger = json.loads(ledger_path.read_text())
        assert list(ledger["requests"]) == [request_id]
        assert ledger["requests"][request_id]["status"] == "PENDING"
        assert ledger["reserved"] == transaction["credits"]

    inspection = inspect_recovery_state(provider)
    assert inspection.state == expected_state

    # Snapshot all persisted evidence before retry.
    evidence_paths = [
        marker_path,
        ledger_path,
        journal_path,
        tmp_path / "provider.json.authorization_history.json",
    ]

    before = {
        str(path): path.read_bytes()
        for path in evidence_paths
        if path.exists()
    }

    with pytest.raises(
        (ProviderCreditStatusUnknown, AuthorizationJournalError)
    ):
        authorize_request(
            provider_state_path=provider,
            local_budget_path=budget,
            now=NOW,
        )

    after = {
        str(path): path.read_bytes()
        for path in evidence_paths
        if path.exists()
    }

    assert after == before
