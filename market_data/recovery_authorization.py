"""Read-only authorization checks for a new recovery request.

Does not authorize HTTP or reserve credits.
Does not modify the historical UNCERTAIN request.
"""

import json
from pathlib import Path

from market_data.authorization_journal import (
    journal_path_for,
    load_journal,
    AuthorizationJournalError,
)
from market_data.unified_request_guard import _load_ledger


class RecoveryAuthorizationBlocked(RuntimeError):
    pass


def check_recovery_accounting(provider_path):
    provider_path = Path(provider_path)

    ledger_path = provider_path.with_name(
        provider_path.name + ".reservations.json"
    )
    journal_path = journal_path_for(provider_path)
    history_path = provider_path.with_name(
        provider_path.name + ".authorization_history.json"
    )
    recovery_path = provider_path.with_name(
        provider_path.name + ".recovery_required.json"
    )

    if recovery_path.exists():
        raise RecoveryAuthorizationBlocked(
            "Existing authorization recovery marker unresolved"
        )

    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except (OSError, ValueError) as exc:
            raise RecoveryAuthorizationBlocked(
                "Authorization history unreadable"
            ) from exc

        if (
            type(history) is not dict
            or history.get("version") != 1
            or history.get("initialized") is not True
            or not ledger_path.exists()
            or not journal_path.exists()
        ):
            raise RecoveryAuthorizationBlocked(
                "Authorization history inconsistent"
            )

    try:
        ledger = _load_ledger(ledger_path)
        journal = load_journal(journal_path)
    except (ValueError, AuthorizationJournalError) as exc:
        raise RecoveryAuthorizationBlocked(
            "Authorization evidence invalid"
        ) from exc

    transactions = journal["transactions"]
    requests = ledger["requests"]

    if (requests or ledger["reserved"]) and not journal_path.exists():
        raise RecoveryAuthorizationBlocked(
            "Reservation evidence without journal"
        )

    if any(
        item["status"] != "FINALIZED"
        for item in transactions.values()
    ):
        raise RecoveryAuthorizationBlocked(
            "Unresolved authorization intent"
        )

    for request_id, transaction in transactions.items():
        reservation = requests.get(request_id)

        if (
            reservation is None
            or reservation["credits"] != transaction["credits"]
        ):
            raise RecoveryAuthorizationBlocked(
                "Journal and ledger mismatch"
            )

    if set(requests) != set(transactions):
        raise RecoveryAuthorizationBlocked(
            "Ledger contains unjournaled requests"
        )

    return {
        "ledger_consistent": True,
        "outstanding_reserved_credits": ledger["reserved"],
        "unresolved_intents": 0,
        "http_authorized": False,
    }
