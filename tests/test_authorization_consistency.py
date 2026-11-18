import copy

import pytest

from market_data.authorization_consistency import check_consistency


REQUEST_ID = "a" * 32
TIMESTAMP = "2026-11-18T10:00:00+00:00"


def evidence():
    journal = {
        "transactions": {
            REQUEST_ID: {
                "status": "FINALIZED",
                "credits": 1,
                "authorized_at": TIMESTAMP,
            }
        }
    }

    ledger = {
        "requests": {
            REQUEST_ID: {
                "status": "PENDING",
                "credits": 1,
                "authorized_at": TIMESTAMP,
            }
        }
    }

    return journal, ledger


def test_consistent_records_remain_unsettled():
    journal, ledger = evidence()
    result = check_consistency(journal, ledger)

    assert result["consistent"] is True
    assert result["pending"] == 1
    assert result["settlement_authorized"] is False


def test_missing_reservation_rejected():
    journal, ledger = evidence()
    ledger["requests"] = {}

    with pytest.raises(ValueError, match="IDs mismatch"):
        check_consistency(journal, ledger)


def test_credit_mismatch_rejected():
    journal, ledger = evidence()
    ledger["requests"][REQUEST_ID]["credits"] = 2

    with pytest.raises(ValueError, match="credits mismatch"):
        check_consistency(journal, ledger)


def test_unresolved_intent_rejected():
    journal, ledger = evidence()
    journal["transactions"][REQUEST_ID]["status"] = "INTENT"

    with pytest.raises(ValueError, match="Unresolved"):
        check_consistency(journal, ledger)


def test_timestamp_mismatch_rejected():
    journal, ledger = evidence()
    ledger["requests"][REQUEST_ID]["authorized_at"] = (
        "2026-11-18T10:01:00+00:00"
    )

    with pytest.raises(ValueError, match="timestamps mismatch"):
        check_consistency(journal, ledger)
