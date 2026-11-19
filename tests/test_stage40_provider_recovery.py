import json
from datetime import datetime, timezone

import pytest

from scripts.run_stage40_provider_recovery import (
    collect,
    diagnose,
    load_probe,
    report,
)

NOW = datetime(2026, 11, 19, 16, 0, tzinfo=timezone.utc)


def setup_files(tmp_path):
    probe = tmp_path / "probe.json"
    source = tmp_path / "snapshot.csv"
    archive = tmp_path / "quarantine"

    attempts = [
        {
            "status": "VERIFIED",
            "started_at": "2026-11-18T18:59:46+00:00",
        },
        {
            "status": "VERIFIED",
            "started_at": "2026-11-18T19:17:00+00:00",
        },
        {
            "status": "VERIFIED",
            "started_at": "2026-11-18T19:23:21+00:00",
        },
        {
            "status": "VERIFIED",
            "started_at": "2026-11-18T19:32:54+00:00",
        },
        {
            "status": "UNCERTAIN",
            "started_at": "2026-11-19T13:06:33+00:00",
        },
    ]

    probe.write_text(json.dumps({
        "version": 1,
        "attempts": attempts,
    }))

    source.write_text(
        "timestamp,Open,High,Low,Close\n"
        "2026-11-19T15:00:00+00:00,1.1,1.2,1.0,1.15\n"
    )

    return probe, source, archive


def test_diagnose_existing_statuses(tmp_path):
    probe, _, _ = setup_files(tmp_path)

    result = diagnose(probe)

    assert result["total_attempts"] == 5
    assert result["verified_count"] == 4
    assert result["uncertain_count"] == 1
    assert result["latest_status"] == "UNCERTAIN"
    assert result["journal_modified"] is False


def test_malformed_journal_rejected(tmp_path):
    probe, _, _ = setup_files(tmp_path)
    probe.write_text('{"version": 1, "attempts": "bad"}')

    with pytest.raises(ValueError):
        load_probe(probe)


def test_collect_quarantines_snapshot(tmp_path):
    probe, source, archive = setup_files(tmp_path)

    before = probe.read_bytes()

    result = collect(source, archive, probe=probe, now=NOW)

    assert result["status"] == "QUARANTINED"
    assert result["provider_attested"] is False
    assert result["directional_signals_allowed"] is False
    assert probe.read_bytes() == before
    assert report(archive)["intact"] == 1


def test_duplicate_archive_does_not_overwrite(tmp_path):
    probe, source, archive = setup_files(tmp_path)

    first = collect(source, archive, probe=probe, now=NOW)
    second = collect(source, archive, probe=probe, now=NOW)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert first["sha256"] == second["sha256"]
    assert report(archive)["snapshots"] == 1


def test_tampered_archive_is_detected(tmp_path):
    probe, source, archive = setup_files(tmp_path)

    result = collect(source, archive, probe=probe, now=NOW)

    from pathlib import Path
    Path(result["csv_path"]).write_text("tampered")

    summary = report(archive)

    assert summary["intact"] == 0
    assert summary["corrupted"] == 1


def test_corrupted_archive_cannot_be_reused(tmp_path):
    probe, source, archive = setup_files(tmp_path)
    result = collect(source, archive, probe=probe, now=NOW)

    from pathlib import Path
    Path(result["csv_path"]).write_text("corrupted")

    with pytest.raises(ValueError, match="hash mismatch"):
        collect(source, archive, probe=probe, now=NOW)


def test_empty_csv_rejected(tmp_path):
    probe, source, archive = setup_files(tmp_path)
    source.write_bytes(b"")

    with pytest.raises(ValueError, match="Empty"):
        collect(source, archive, probe=probe, now=NOW)


def test_missing_probe_rejected(tmp_path):
    probe, source, archive = setup_files(tmp_path)
    probe.unlink()

    with pytest.raises(ValueError, match="missing"):
        collect(source, archive, probe=probe, now=NOW)


def test_empty_report(tmp_path):
    result = report(tmp_path / "does_not_exist")

    assert result["snapshots"] == 0
    assert result["verified_live_snapshots"] == 0


def test_naive_time_rejected(tmp_path):
    probe, source, archive = setup_files(tmp_path)

    with pytest.raises(ValueError, match="Timezone"):
        collect(
            source,
            archive,
            probe=probe,
            now=datetime(2026, 11, 19, 16, 0),
        )
