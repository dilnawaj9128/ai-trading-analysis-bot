"""Offline safety tests for the new Stage 52D recovery route."""

import json
from pathlib import Path

import pytest

from market_data.recovery_case import build_case
from scripts import run_stage52d_new_recovery_probe as recovery


@pytest.fixture
def setup_recovery(tmp_path, monkeypatch):
    root = tmp_path / "api"
    reports = tmp_path / "reports"
    root.mkdir()
    reports.mkdir()

    evidence = {
        "approved_research_probe.json": {
            "version": 1,
            "attempts": [{
                "status": "UNCERTAIN",
                "started_at": "2026-11-19T13:06:33+00:00",
            }],
        },
        "credit_refresh_execution.json": {
            "version": 1,
            "status": "UNCERTAIN",
        },
        "credit_refresh_lifecycle.json": {
            "version": 1,
            "status": "CLAIMED",
        },
        "provider_credits.json": {
            "version": 1,
            "observed_at": "2026-11-18T19:32:55+00:00",
            "credits_used": 1,
            "credits_left": 7,
        },
    }

    for name, payload in evidence.items():
        (root / name).write_text(json.dumps(payload))

    case = reports / "case.json"
    case.write_text(json.dumps(build_case(root)))

    archive = reports / "historical.json"
    archive.write_bytes((root / "provider_credits.json").read_bytes())

    monkeypatch.setattr(recovery, "ROOT", root)
    monkeypatch.setattr(
        recovery, "OLD", root / "approved_research_probe.json"
    )
    monkeypatch.setattr(recovery, "CASE", case)
    monkeypatch.setattr(recovery, "ARCHIVE", archive)
    monkeypatch.setattr(
        recovery, "CLAIM", root / "recovery_claim.json"
    )
    monkeypatch.setattr(
        recovery, "NEW_JOURNAL", root / "new_probe.json"
    )
    monkeypatch.setattr(
        recovery, "BUDGET", root / "budget.json"
    )
    monkeypatch.setattr(
        recovery, "PROVIDER", root / "provider_credits.json"
    )
    monkeypatch.setattr(
        recovery, "CSV", tmp_path / "candles.csv"
    )

    monkeypatch.setenv("TWELVE_DATA_API_KEY", "OFFLINE_FAKE_KEY")

    calls = []

    def fake_probe_once(**kwargs):
        calls.append(kwargs)
        return {
            "status": "VERIFIED",
            "candles": 10,
            "credits_left": 7,
            "csv_path": str(tmp_path / "candles.csv"),
        }

    monkeypatch.setattr(recovery, "probe_once", fake_probe_once)

    return root, case, calls


def test_preview_never_executes_request(setup_recovery):
    root, case, calls = setup_recovery

    recovery.run(False)

    assert calls == []
    assert not recovery.CLAIM.exists()


def test_new_request_claim_is_single_use(setup_recovery):
    root, case, calls = setup_recovery

    recovery.run(True)

    assert len(calls) == 1
    assert recovery.CLAIM.exists()

    with pytest.raises(recovery.ProbeBlocked):
        recovery.run(True)

    assert len(calls) == 1


def test_old_uncertain_evidence_preserved(setup_recovery):
    root, case, calls = setup_recovery

    old = recovery.OLD
    before = old.read_bytes()

    recovery.run(True)

    assert old.read_bytes() == before
    assert json.loads(old.read_text())["attempts"][-1][
        "status"
    ] == "UNCERTAIN"


def test_changed_recovery_case_blocks(setup_recovery):
    root, case, calls = setup_recovery

    data = json.loads(case.read_text())
    data["probe_started_at"] = "2020-01-01T00:00:00+00:00"
    case.write_text(json.dumps(data))

    with pytest.raises(recovery.ProbeBlocked):
        recovery.run(True)

    assert calls == []
    assert not recovery.CLAIM.exists()


def test_provider_snapshot_change_blocks(setup_recovery):
    root, case, calls = setup_recovery

    provider = recovery.PROVIDER
    data = json.loads(provider.read_text())
    data["credits_left"] = 999
    provider.write_text(json.dumps(data))

    with pytest.raises(recovery.ProbeBlocked):
        recovery.run(True)

    assert calls == []
    assert not recovery.CLAIM.exists()


def test_failure_does_not_allow_retry(setup_recovery, monkeypatch):
    root, case, calls = setup_recovery

    attempts = []

    def fail_once(**kwargs):
        attempts.append(1)
        raise TimeoutError("simulated offline timeout")

    monkeypatch.setattr(recovery, "probe_once", fail_once)

    with pytest.raises(TimeoutError):
        recovery.run(True)

    assert recovery.CLAIM.exists()

    with pytest.raises(recovery.ProbeBlocked):
        recovery.run(True)

    assert len(attempts) == 1
