"""Stage 51 safety, evidence persistence and integrity tests."""
import json
from datetime import datetime, timezone

import pytest

from research.stage51_forward_recorder import (
    build_record,
    save_record,
    verify_record,
)


def test_uncertain_probe_fails_closed(tmp_path):
    journal = tmp_path / "probe.json"
    journal.write_text(json.dumps({
        "version": 1,
        "attempts": [{
            "status": "UNCERTAIN",
            "started_at": "2026-11-19T13:06:33+00:00",
        }],
    }))

    record = build_record(
        now=datetime(2026, 11, 19, 17, 0, tzinfo=timezone.utc),
        probe_path=journal,
        csv_path=tmp_path / "missing.csv",
    )

    assert record["signal"] == "NO TRADE"
    assert record["authorization"] == "BLOCKED"
    assert record["execution_enabled"] is False
    assert record["prediction_generated"] is False


def test_create_only_record_and_checksum(tmp_path):
    record = build_record(
        probe_path=tmp_path / "missing_probe.json",
        csv_path=tmp_path / "missing.csv",
    )

    path = save_record(record, output_dir=tmp_path / "records")
    assert verify_record(path)

    with pytest.raises(FileExistsError):
        save_record(record, output_dir=tmp_path / "records")


def test_modified_evidence_detected(tmp_path):
    record = build_record(
        probe_path=tmp_path / "missing_probe.json",
        csv_path=tmp_path / "missing.csv",
    )

    path = save_record(record, output_dir=tmp_path / "records")
    envelope = json.loads(path.read_text())
    envelope["record"]["signal"] = "UP"
    path.write_text(json.dumps(envelope))

    assert verify_record(path) is False
