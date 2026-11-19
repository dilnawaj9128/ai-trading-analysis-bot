"""Stage 51B source identity, deduplication and safety."""

import json

import pytest

from research.stage51_forward_observation import (
    build_observation,
    record_observation,
)


def test_missing_sources_fail_closed(tmp_path):
    record = build_observation(
        csv_path=tmp_path / "missing.csv",
        probe_path=tmp_path / "missing_probe.json",
    )

    assert record["signal"] == "NO TRADE"
    assert record["authorization"] == "BLOCKED"
    assert record["prediction_generated"] is False
    assert record["provider_origin_verified"] is False
    assert "CSV_SOURCE_UNAVAILABLE" in record["reasons"]


def test_same_evidence_not_duplicated(tmp_path):
    options = dict(
        csv_path=tmp_path / "missing.csv",
        probe_path=tmp_path / "missing_probe.json",
        output_dir=tmp_path / "decisions",
    )

    first, first_path, created1 = record_observation(**options)
    second, second_path, created2 = record_observation(**options)

    assert created1 is True
    assert created2 is False
    assert first_path == second_path
    assert first["decision_id"] == second["decision_id"]

    assert len(list(
        (tmp_path / "decisions").glob("*.json")
    )) == 1


def test_probe_change_creates_new_observation(tmp_path):
    journal = tmp_path / "probe.json"
    options = dict(
        csv_path=tmp_path / "missing.csv",
        probe_path=journal,
        output_dir=tmp_path / "decisions",
    )

    first, _, _ = record_observation(**options)

    journal.write_text(json.dumps({
        "version": 1,
        "attempts": [],
    }))

    second, _, created = record_observation(**options)

    assert created is True
    assert first["decision_id"] != second["decision_id"]
    assert second["signal"] == "NO TRADE"


def test_tampered_observation_rejected(tmp_path):
    options = dict(
        csv_path=tmp_path / "missing.csv",
        probe_path=tmp_path / "missing_probe.json",
        output_dir=tmp_path / "decisions",
    )

    _, path, _ = record_observation(**options)

    envelope = json.loads(path.read_text())
    envelope["record"]["signal"] = "UP"
    path.write_text(json.dumps(envelope))

    with pytest.raises(ValueError):
        record_observation(**options)
