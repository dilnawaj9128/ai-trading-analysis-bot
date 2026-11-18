"""Offline request reconciliation checks.

No HTTP, file writes, settlement, or trading execution.
"""

from market_data.authorization_consistency import (
    check_consistency,
)
from market_data.request_response_evidence import (
    validate_response_evidence,
)


def evaluate_offline_response(
    *,
    request_id,
    journal,
    ledger,
    response_status,
    response_headers,
):
    """Cross-check an existing request against simulated HTTP evidence."""

    consistency = check_consistency(journal, ledger)

    requests = ledger["requests"]
    transactions = journal["transactions"]

    if request_id not in requests:
        raise ValueError("Request ID missing from reservation ledger")

    if request_id not in transactions:
        raise ValueError("Request ID missing from journal")

    evidence = validate_response_evidence(
        request_id=request_id,
        reservation=requests[request_id],
        journal_transaction=transactions[request_id],
        response_status=response_status,
        response_headers=response_headers,
    )

    return {
        "consistent": consistency["consistent"],
        "request_id": request_id,
        "response_structurally_valid": evidence["structurally_valid"],
        "provider_credits_left": evidence["provider_credits_left"],
        "trusted_provider_provenance": False,
        "settlement_authorized": False,
        "completion_authorized": False,
        "analysis_only": True,
    }
