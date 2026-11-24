"""Read-only Stage 52D recovery blocker audit.

Never sends HTTP, grants authorization, changes journals, or settles an
UNCERTAIN request. Report only non-secret fields and fingerprints.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/api_usage")
REPORTS = Path("data/recovery_reports")


def _json(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or symlinked evidence: " + path.name)
    data = json.loads(path.read_text(encoding="utf-8"))
    if type(data) is not dict:
        raise ValueError("Invalid evidence structure: " + path.name)
    return data


def _sha(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("Symlinked evidence: " + path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root: Path = ROOT, reports: Path = REPORTS, *,
          now: datetime | None = None) -> dict:
    root, reports = Path(root), Path(reports)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware now required")
    now = now.astimezone(timezone.utc)

    old_path = root / "approved_research_probe.json"
    current_path = root / "provider_credits.json"
    archive_path = reports / "stage52d_historical_provider_credits.json"
    case_path = reports / "stage52d_20261119_uncertain_case.json"
    new_path = root / "stage52d_new_recovery_probe.json"
    claim_path = root / "stage52d_new_recovery_claim.json"

    old, current, archive, case = map(_json, (
        old_path, current_path, archive_path, case_path
    ))
    expected = case.get("source_sha256")
    if type(expected) is not dict:
        raise ValueError("Recovery case lacks fingerprints")
    originals = {
        "probe": old_path,
        "execution": root / "credit_refresh_execution.json",
        "lifecycle": root / "credit_refresh_lifecycle.json",
        "provider": archive_path,
    }
    historical_hashes_match = all(
        _sha(path) == expected.get(name)
        for name, path in originals.items()
    )

    attempts = old.get("attempts")
    original_uncertain = (
        type(attempts) is list and bool(attempts)
        and attempts[-1].get("status") == "UNCERTAIN"
        and attempts[-1].get("started_at") == case.get("probe_started_at")
    )

    def observation(payload):
        if payload.get("version") != 1:
            raise ValueError("Invalid provider snapshot version")
        observed = datetime.fromisoformat(payload["observed_at"])
        if observed.tzinfo is None:
            raise ValueError("Naive provider snapshot")
        for k in ("credits_used", "credits_left"):
            if type(payload.get(k)) is not int or payload[k] < 0:
                raise ValueError("Invalid snapshot count")
        return observed.astimezone(timezone.utc)

    current_time, archive_time = observation(current), observation(archive)
    if current_time > now:
        raise ValueError("Provider snapshot timestamp is in the future")

    if new_path.exists():
        new = _json(new_path)
        attempts_new = new.get("attempts")
        new_state = (
            "EMPTY_EXISTING_JOURNAL"
            if new.get("version") == 1
            and type(attempts_new) is list and len(attempts_new) == 0
            else "NONEMPTY_OR_INVALID_JOURNAL"
        )
    else:
        new_state = "MISSING"

    blockers = []
    if not historical_hashes_match:
        blockers.append("HISTORICAL_EVIDENCE_MISMATCH")
    if not original_uncertain:
        blockers.append("OLD_PROBE_STATE_CHANGED")
    if _sha(current_path) != _sha(archive_path):
        blockers.append("CURRENT_SNAPSHOT_DIFFERS_FROM_ARCHIVE")
    if new_state != "MISSING":
        blockers.append("NEW_RECOVERY_JOURNAL_ALREADY_EXISTS")
    if claim_path.exists():
        blockers.append("RECOVERY_CLAIM_EXISTS")
    if (now - current_time).total_seconds() > 300:
        blockers.append("PROVIDER_SNAPSHOT_STALE")

    return {
        "historical_evidence_matches": historical_hashes_match,
        "old_probe_uncertain": original_uncertain,
        "archived_snapshot_at": archive_time.isoformat(),
        "current_snapshot_at": current_time.isoformat(),
        "current_snapshot_newer": current_time > archive_time,
        "current_credits_left_recorded": current["credits_left"],
        "archive_credits_left_recorded": archive["credits_left"],
        "new_journal_state": new_state,
        "claim_exists": claim_path.exists(),
        "blockers": blockers,
        "old_request_verified": False,
        "new_http_authorized": False,
        "retry_allowed": False,
        "trading_enabled": False,
    }


def main():
    try:
        result = audit()
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("AUDIT BLOCKED:", type(exc).__name__, str(exc))
        raise SystemExit(1)
    finally:
        print("READ-ONLY: no HTTP, journal edits, credit updates or authorization.")


if __name__ == "__main__":
    main()
