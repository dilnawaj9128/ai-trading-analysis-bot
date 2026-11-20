import json

import pytest

from market_data.recovery_authorization import (
    check_recovery_accounting,
    RecoveryAuthorizationBlocked,
)


def test_empty_ledger_is_consistent(tmp_path):
    provider = tmp_path / "provider_credits.json"
    result = check_recovery_accounting(provider)

    assert result["ledger_consistent"] is True
    assert result["http_authorized"] is False


def test_unresolved_marker_blocks(tmp_path):
    provider = tmp_path / "provider_credits.json"
    marker = tmp_path / "provider_credits.json.recovery_required.json"
    marker.write_text("{}")

    with pytest.raises(RecoveryAuthorizationBlocked):
        check_recovery_accounting(provider)


def test_unresolved_intent_blocks(tmp_path):
    provider = tmp_path / "provider_credits.json"
    request_id = "a" * 32

    ledger = {
        "version": 2,
        "reserved": 1,
        "legacy_reserved": 0,
        "requests": {
            request_id: {
                "credits": 1,
                "status": "PENDING"
            }
        },
    }

    journal = {
        "version": 1,
        "transactions": {
            request_id: {
                "status": "INTENT",
                "credits": 1,
                "authorized_at": "2026-11-19T13:00:00+00:00",
            }
        },
    }

    (tmp_path / "provider_credits.json.reservations.json").write_text(
        json.dumps(ledger)
    )
    (tmp_path / "provider_credits.json.authorization_journal.json").write_text(
        json.dumps(journal)
    )

    with pytest.raises(RecoveryAuthorizationBlocked):
        check_recovery_accounting(provider)
