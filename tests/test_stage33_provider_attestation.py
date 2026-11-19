"""Stage 33 provenance tests: no network calls or trading."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from research.stage33_provider_attestation import evaluate_attested_snapshot

NOW = datetime(2026, 11, 19, 15, 30, tzinfo=timezone.utc)


def fixture(tmp_path, *, old=False):
    csv = tmp_path / "candles.csv"
    csv.write_text("timestamp,Open,High,Low,Close\n2026-11-19T15:28:00+00:00,1.1,1.2,1.0,1.15\n", encoding="utf8")
    journal = tmp_path / "probe.json"
    attempt = {
        "status": "VERIFIED", "csv_sha256": hashlib.sha256(csv.read_bytes()).hexdigest(),
        "csv_path": str(csv.resolve()), "provider": "twelve_data",
        "symbol": "EUR/USD", "timeframe": "1min", "candles": 1,
        "verified_at_utc": NOW.isoformat()
    }
    if old:
        del attempt["csv_sha256"]
    journal.write_text(json.dumps({"version": 1, "attempts": [attempt]}), encoding="utf8")
    return csv, journal


def test_attested_source_still_blocks_unknown_feed_mode(tmp_path):
    csv, journal = fixture(tmp_path)
    result = evaluate_attested_snapshot(csv, journal, observed_at=NOW)
    assert result["provider_attested"] is True
    assert result["signal"] == "NO TRADE"
    assert result["status"] == "BLOCKED"
    assert "Feed mode" in result["reason"]


def test_modified_csv_is_blocked(tmp_path):
    csv, journal = fixture(tmp_path)
    csv.write_text(csv.read_text() + "\n")
    result = evaluate_attested_snapshot(csv, journal, observed_at=NOW)
    assert result["provider_attested"] is False
    assert "changed" in result["reason"]


def test_legacy_journal_without_hash_fails_closed(tmp_path):
    csv, journal = fixture(tmp_path, old=True)
    result = evaluate_attested_snapshot(csv, journal, observed_at=NOW)
    assert result["status"] == "BLOCKED"
    assert result["provider_attested"] is False


def test_unresolved_latest_attempt_blocks(tmp_path):
    csv, journal = fixture(tmp_path)
    payload = json.loads(journal.read_text())
    payload["attempts"].append({"status": "UNCERTAIN"})
    journal.write_text(json.dumps(payload))
    result = evaluate_attested_snapshot(csv, journal, observed_at=NOW)
    assert "unresolved" in result["reason"]


def test_stale_attestation_blocks(tmp_path):
    csv, journal = fixture(tmp_path)
    result = evaluate_attested_snapshot(csv, journal, observed_at=NOW + timedelta(minutes=4))
    assert result["provider_attested"] is False
    assert "stale" in result["reason"]


def test_future_attestation_blocks(tmp_path):
    csv, journal = fixture(tmp_path)
    result = evaluate_attested_snapshot(csv, journal, observed_at=NOW - timedelta(seconds=1))
    assert result["provider_attested"] is False
    assert "future" in result["reason"]


def test_mismatched_path_blocks(tmp_path):
    csv, journal = fixture(tmp_path)
    other = tmp_path / "other.csv"
    other.write_bytes(csv.read_bytes())
    result = evaluate_attested_snapshot(other, journal, observed_at=NOW)
    assert result["provider_attested"] is False
    assert "path mismatch" in result["reason"]


def test_absent_journal_blocks(tmp_path):
    csv, journal = fixture(tmp_path)
    journal.unlink()
    result = evaluate_attested_snapshot(csv, journal, observed_at=NOW)
    assert result["signal"] == "NO TRADE"
    assert result["status"] == "BLOCKED"
