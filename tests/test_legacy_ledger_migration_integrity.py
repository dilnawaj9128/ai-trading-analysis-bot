import json

import pytest

from market_data.unified_request_guard import _load_ledger


def test_legacy_migration_preserves_reserved_credits(tmp_path):
    ledger_path = tmp_path / "ledger.json"

    ledger_path.write_text(
        json.dumps({
            "version": 1,
            "reserved": 3,
        }),
        encoding="utf-8",
    )

    before = ledger_path.read_bytes()

    migrated = _load_ledger(ledger_path)

    assert migrated["version"] == 2
    assert migrated["reserved"] == 3
    assert migrated["legacy_reserved"] == 3
    assert migrated["requests"] == {}

    # Loading must not mutate the original file.
    assert ledger_path.read_bytes() == before


def test_legacy_migration_rejects_unexpected_requests(tmp_path):
    ledger_path = tmp_path / "ledger.json"

    ledger_path.write_text(
        json.dumps({
            "version": 1,
            "reserved": 3,
            "requests": {
                "unknown-request": {
                    "credits": 2,
                    "status": "PENDING",
                }
            },
        }),
        encoding="utf-8",
    )

    before = ledger_path.read_bytes()

    with pytest.raises(ValueError, match="legacy|ledger"):
        _load_ledger(ledger_path)

    assert ledger_path.read_bytes() == before
