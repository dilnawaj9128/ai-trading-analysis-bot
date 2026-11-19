"""Stage 52D: offline recovery must preserve uncertainty."""

import json

import pytest

from market_data.uncertain_recovery import (
    RecoveryEvidenceError,
    assess_recovery,
)


def prepare(tmp_path, probe_status="UNCERTAIN"):
    files = {
        "probe": tmp_path / "probe.json",
        "execution": tmp_path / "execution.json",
        "lifecycle": tmp_path / "lifecycle.json",
        "provider": tmp_path / "provider.json",
    }

    payloads = {
        "probe": {
            "version": 1,
            "attempts": [{
                "status": probe_status,
                "started_at": "2026-11-19T13:06:33+00:00",
            }],
        },
        "execution": {
            "version": 1,
            "status": "UNCERTAIN",
        },
        "lifecycle": {
            "version": 1,
            "status": "CLAIMED",
        },
        "provider": {
            "version": 1,
            "credits_left": 7,
            "observed_at": "2026-11-18T19:32:55+00:00",
        },
    }

    for name, path in files.items():
        path.write_text(json.dumps(payloads[name]))

    return files


def assess(files):
    return assess_recovery(
        probe_path=files["probe"],
        execution_path=files["execution"],
        lifecycle_path=files["lifecycle"],
        provider_path=files["provider"],
    )


def test_uncertain_remains_unresolved(tmp_path):
    files = prepare(tmp_path)
    result = assess(files)

    assert result["classification"] == "UNRESOLVED_ACCOUNTING"
    assert result["historical_request_verified"] is False
    assert result["new_api_request_authorized"] is False
    assert result["retry_allowed"] is False


def test_inspection_does_not_modify_evidence(tmp_path):
    files = prepare(tmp_path)
    before = {
        name: path.read_bytes()
        for name, path in files.items()
    }

    assess(files)

    for name, path in files.items():
        assert path.read_bytes() == before[name]


def test_invalid_probe_fails_closed(tmp_path):
    files = prepare(tmp_path)
    files["probe"].write_text("{invalid")

    with pytest.raises(RecoveryEvidenceError):
        assess(files)


def test_missing_execution_fails_closed(tmp_path):
    files = prepare(tmp_path)
    files["execution"].unlink()

    with pytest.raises(RecoveryEvidenceError):
        assess(files)
