"""Read-only authorization health checks. No HTTP or state writes."""

from pathlib import Path

from market_data.provider_credit_state import DEFAULT_PATH
from market_data.credit_dashboard_status import (
    get_credit_dashboard_status,
)
from market_data.authorization_journal import (
    journal_path_for,
    load_journal,
)
from market_data.unified_request_guard import _load_ledger
from market_data.authorization_consistency import check_consistency


def get_authorization_health(provider_path=DEFAULT_PATH):
    provider = Path(provider_path)
    journal = journal_path_for(provider)
    ledger = provider.with_name(
        provider.name + ".reservations.json"
    )
    history = provider.with_name(
        provider.name + ".authorization_history.json"
    )
    recovery = provider.with_name(
        provider.name + ".recovery_required.json"
    )

    report = {
        "provider_status": "UNKNOWN",
        "evidence_status": "REVIEW_REQUIRED",
        "pending": 0,
        "uncertain": 0,
        "reserved_credits": None,
        "recovery_marker": recovery.exists(),
        "live_fetch_authorized": False,
        "reason": "Not yet evaluated",
    }

    try:
        credit = get_credit_dashboard_status(path=provider)
        report["provider_status"] = credit["status"]
    except (OSError, ValueError, TypeError, KeyError):
        report["reason"] = "Provider state invalid"
        return report

    if recovery.exists():
        report["reason"] = "Recovery marker present"
        return report

    # Missing journal/ledger is not proof of corruption.
    if not journal.exists() and not ledger.exists() and not history.exists():
        report["evidence_status"] = "POSSIBLE_FIRST_RUN"
        report["reserved_credits"] = 0
        report["reason"] = "No authorization history found"
        return report

    if not journal.exists() or not ledger.exists() or not history.exists():
        report["reason"] = "Incomplete authorization evidence"
        return report

    try:
        journal_data = load_journal(journal)
        ledger_data = _load_ledger(ledger)
        result = check_consistency(journal_data, ledger_data)

        requests = ledger_data["requests"]
        reserved = ledger_data["reserved"]
        legacy = ledger_data["legacy_reserved"]

        outstanding = legacy + sum(
            entry["credits"]
            for entry in requests.values()
            if entry["status"] in ("PENDING", "UNCERTAIN")
        )

        if outstanding != reserved:
            report["reason"] = "Reserved credit totals mismatch"
            return report

        report["evidence_status"] = "CONSISTENT"
        report["pending"] = result["pending"]
        report["uncertain"] = result["uncertain"]
        report["reserved_credits"] = reserved
        report["reason"] = "Local journal and ledger consistent"

    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        report["reason"] = "Authorization evidence validation failed"

    # This health report never grants API authorization.
    return report
