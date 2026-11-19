import hashlib
import json

import pytest

from market_data.recovery_credit_archive import (
    CreditArchiveError,
    archive_historical_credits,
)


def setup_files(tmp_path):
    provider = tmp_path / "provider_credits.json"
    case = tmp_path / "case.json"
    archive = tmp_path / "archive" / "historical.json"

    original = {
        "version": 1,
        "observed_at": "2026-11-18T19:32:55+00:00",
        "credits_left": 7,
        "credits_used": 1,
    }

    provider.write_text(json.dumps(original))
    digest = hashlib.sha256(provider.read_bytes()).hexdigest()

    case.write_text(json.dumps({
        "schema_version": 1,
        "classification": "UNRESOLVED_ACCOUNTING",
        "source_sha256": {"provider": digest},
    }))

    return case, provider, archive


def run(case, provider, archive):
    return archive_historical_credits(
        case_path=case,
        provider_path=provider,
        archive_path=archive,
    )


def test_preserves_exact_original_bytes(tmp_path):
    case, provider, archive = setup_files(tmp_path)
    original = provider.read_bytes()

    result = run(case, provider, archive)

    assert archive.read_bytes() == original
    assert provider.read_bytes() == original
    assert result["new_api_request_authorized"] is False
    assert result["http_requests"] == 0


def test_duplicate_archive_cannot_overwrite(tmp_path):
    case, provider, archive = setup_files(tmp_path)

    run(case, provider, archive)
    original = archive.read_bytes()

    with pytest.raises(CreditArchiveError, match="already"):
        run(case, provider, archive)

    assert archive.read_bytes() == original


def test_modified_provider_snapshot_blocked(tmp_path):
    case, provider, archive = setup_files(tmp_path)

    data = json.loads(provider.read_text())
    data["credits_left"] = 999
    provider.write_text(json.dumps(data))

    with pytest.raises(CreditArchiveError, match="fingerprint"):
        run(case, provider, archive)

    assert not archive.exists()


def test_invalid_case_blocked(tmp_path):
    case, provider, archive = setup_files(tmp_path)
    case.write_text("{invalid")

    with pytest.raises(CreditArchiveError):
        run(case, provider, archive)


def test_source_cannot_be_archive_destination(tmp_path):
    case, provider, _ = setup_files(tmp_path)

    with pytest.raises(CreditArchiveError, match="separate"):
        run(case, provider, provider)
