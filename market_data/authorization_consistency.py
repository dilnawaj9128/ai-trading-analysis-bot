"""Read-only cross-checks for already validated journal/ledger data.

Does not settle reservations, authorize requests or perform HTTP.
"""


def check_consistency(journal, ledger):
    if not isinstance(journal, dict) or not isinstance(ledger, dict):
        raise ValueError("Invalid authorization evidence")

    transactions = journal.get("transactions")
    requests = ledger.get("requests")

    if not isinstance(transactions, dict):
        raise ValueError("Invalid journal transactions")

    if not isinstance(requests, dict):
        raise ValueError("Invalid ledger requests")

    if set(transactions) != set(requests):
        raise ValueError("Journal and ledger request IDs mismatch")

    for request_id, transaction in transactions.items():
        reservation = requests[request_id]

        if not isinstance(transaction, dict):
            raise ValueError("Invalid journal transaction")

        if not isinstance(reservation, dict):
            raise ValueError("Invalid reservation")

        if transaction.get("status") != "FINALIZED":
            raise ValueError("Unresolved authorization intent")

        if transaction.get("credits") != reservation.get("credits"):
            raise ValueError("Reservation credits mismatch")

        if transaction.get("authorized_at") != reservation.get(
            "authorized_at"
        ):
            raise ValueError("Authorization timestamps mismatch")

    pending = sum(
        1 for item in requests.values()
        if item.get("status") == "PENDING"
    )

    uncertain = sum(
        1 for item in requests.values()
        if item.get("status") == "UNCERTAIN"
    )

    return {
        "consistent": True,
        "total_requests": len(requests),
        "pending": pending,
        "uncertain": uncertain,
        "settlement_authorized": False,
    }
