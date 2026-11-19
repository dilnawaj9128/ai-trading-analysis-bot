"""Stage 52D Part 3 recovery case tests."""

import json
import pytest

from market_data.recovery_case import (
    build_case,
    save_case_exclusive,
)


def make_evidence(tmp_path):
    payloads = {
        "approved_research_probe.json": {
            "version": 1,
            "attempts": [{
                "status": "UNCERTAIN",
                "started_at": "2026-11-19T13:06:33+00:00",
            }],
        },
        "credit_refresh_execution.json": {
            "status": "UNCERTAIN",
        },
        "credit_refresh_lifecycle.json": {
            "status": "CLAIMED",
        },
        "provider_credits.json": {
            "credits_left": 7,
            "observed_at": "2026-11-18T19:32:55+00:00",
        },
    }

    for name, content in payloads.items():
        (tmp_path / name).write_text(json.dumps(content))

    return tmp_path


def test_case_preserves_uncertainty(tmp_path):
    root = make_evidence(tmp_path)
    case = build_case(root)

    assert case["classification"] == "UNRESOLVED_ACCOUNTING"
    assert case["decision"]["old_request_verified"] is False
    assert case["decision"]["retry_allowed"] is False
    assert case["decision"]["new_api_request_authorized"] is False
    assert case["provider_observation"]["request_specific_match"] is False


def test_source_journals_never_modified(tmp_path):
    root = make_evidence(tmp_path)

    before = {
        path.name: path.read_bytes()
        for path in root.glob("*.json")
    }

    case = build_case(root)

    destination = (
        tmp_path / "reports" / "case.json"
    )
    save_case_exclusive(case, destination)

    assert destination.exists()

    for name, original in before.items():
        assert (root / name).read_bytes() == original


def test_duplicate_case_cannot_overwrite(tmp_path):
    root = make_evidence(tmp_path)
    case = build_case(root)

    destination = tmp_path / "case.json"
    save_case_exclusive(case, destination)

    original = destination.read_bytes()

    with pytest.raises(FileExistsError):
        save_case_exclusive(case, destination)

    assert destination.read_bytes() == original
