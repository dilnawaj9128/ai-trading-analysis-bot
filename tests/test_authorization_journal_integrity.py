import json

import pytest

from market_data.authorization_journal import (
    AuthorizationJournalError,
    load_journal,
)


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 1, "transactions": []},
        {"version": 2, "transactions": {}},
        {"version": 1, "transactions": {"abc": "invalid"}},
        {
            "version": 1,
            "transactions": {
                "a" * 32: {
                    "status": "UNKNOWN",
                    "credits": 1,
                    "authorized_at": "2026-11-13T12:00:00+00:00",
                }
            },
        },
        {
            "version": 1,
            "transactions": {
                "a" * 32: {
                    "status": "INTENT",
                    "credits": -1,
                    "authorized_at": "2026-11-13T12:00:00+00:00",
                }
            },
        },
        {
            "version": 1,
            "transactions": {
                "a" * 32: {
                    "status": "FINALIZED",
                    "credits": 1,
                    "authorized_at": "invalid-date",
                }
            },
        },
    ],
)
def test_invalid_journal_metadata_fails_closed(tmp_path, payload):
    journal = tmp_path / "journal.json"
    journal.write_text(json.dumps(payload))

    with pytest.raises(AuthorizationJournalError):
        load_journal(journal)
