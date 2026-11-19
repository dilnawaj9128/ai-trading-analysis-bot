import hashlib
import json

import pytest

from scripts.run_stage41_evidence_audit import (
    audit,
    load_probe,
    write_evidence_report,
)


def sample(tmp_path):
    probe = tmp_path / "probe.json"
    csv = tmp_path / "candles.csv"

    csv.write_text(
        "timestamp,Open,High,Low,Close\n"
        "2026-11-19T12:00:00+00:00,1.1,1.2,1.0,1.15\n"
    )

    attempts = [
        {
            "status": "VERIFIED",
            "started_at": "2026-11-18T18:59:46+00:00",
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

    return probe, csv


def test_unresolved_latest_blocks(tmp_path):
    probe, csv = sample(tmp_path)
    result = audit(probe=probe, csv=csv)

    assert result["latest_status"] == "UNCERTAIN"
    assert result["recovery_required"] is True
    assert result["directional_analysis_authorized"] is False


def test_legacy_verified_not_promoted(tmp_path):
    probe, csv = sample(tmp_path)
    result = audit(probe=probe, csv=csv)

    assert result["attempts"][0]["evidence"] == (
        "LEGACY_VERIFIED_NO_HASH"
    )


def test_uncertain_not_promoted(tmp_path):
    probe, csv = sample(tmp_path)
    result = audit(probe=probe, csv=csv)

    assert result["attempts"][1]["evidence"] == (
        "UNRESOLVED_REQUEST"
    )


def test_original_journal_unchanged(tmp_path):
    probe, csv = sample(tmp_path)
    before = probe.read_bytes()

    audit(probe=probe, csv=csv)

    assert probe.read_bytes() == before


def test_matching_hash_not_live_authorization(tmp_path):
    probe, csv = sample(tmp_path)
    payload = json.loads(probe.read_text())

    payload["attempts"] = [{
        "status": "VERIFIED",
        "started_at": "2026-11-19T12:00:00+00:00",
        "csv_sha256": hashlib.sha256(
            csv.read_bytes()
        ).hexdigest(),
        "provider": "twelve_data",
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "csv_path": str(csv.resolve()),
    }]

    probe.write_text(json.dumps(payload))
    result = audit(probe=probe, csv=csv)

    assert result["attempts"][0]["evidence"] == (
        "LOCAL_HASH_MATCH"
    )
    assert result["provider_feed_mode"] == "UNKNOWN"
    assert result["directional_analysis_authorized"] is False


def test_tampered_csv_hash_mismatch(tmp_path):
    probe, csv = sample(tmp_path)
    payload = json.loads(probe.read_text())

    payload["attempts"] = [{
        "status": "VERIFIED",
        "started_at": "2026-11-19T12:00:00+00:00",
        "csv_sha256": hashlib.sha256(
            csv.read_bytes()
        ).hexdigest(),
        "provider": "twelve_data",
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "csv_path": str(csv.resolve()),
    }]

    probe.write_text(json.dumps(payload))
    csv.write_text("tampered")

    result = audit(probe=probe, csv=csv)

    assert result["attempts"][0]["evidence"] == (
        "CSV_HASH_MISMATCH"
    )


def test_export_report_without_overwrite(tmp_path):
    probe, csv = sample(tmp_path)
    result = audit(probe=probe, csv=csv)

    out = tmp_path / "reports"

    first, created = write_evidence_report(result, out)
    second, duplicate = write_evidence_report(result, out)

    assert created is True
    assert duplicate is False
    assert first == second


def test_export_corruption_detected(tmp_path):
    probe, csv = sample(tmp_path)
    result = audit(probe=probe, csv=csv)

    out = tmp_path / "reports"
    path, _ = write_evidence_report(result, out)

    path.write_text("corrupted")

    with pytest.raises(ValueError, match="corrupted"):
        write_evidence_report(result, out)


def test_bad_journal_rejected(tmp_path):
    probe, csv = sample(tmp_path)
    probe.write_text('{"version":1,"attempts":"bad"}')

    with pytest.raises(ValueError):
        load_probe(probe)


def test_naive_timestamp_rejected(tmp_path):
    probe, csv = sample(tmp_path)
    payload = json.loads(probe.read_text())

    payload["attempts"][0]["started_at"] = (
        "2026-11-19T12:00:00"
    )
    probe.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="Timezone"):
        audit(probe=probe, csv=csv)
