"""Stage 40: offline provider recovery and quarantined snapshot archive.

No HTTP requests, no API credits, no order execution.
Never changes the approved-probe journal or asserts live feed provenance.
"""

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PROBE = Path("data/api_usage/approved_research_probe.json")
SOURCE = Path("data/real_market/latest_eurusd_completed.csv")
ARCHIVE = Path("data/quarantine/stage40")

STATUSES = {
    "INTENT", "BUDGET_RESERVED",
    "REQUEST_ATTEMPTED", "VERIFIED", "UNCERTAIN",
}


def utc_now():
    return datetime.now(timezone.utc)


def load_probe(path=PROBE):
    """Read request statuses without editing any provider state."""
    path = Path(path)

    if not path.is_file():
        raise ValueError("Probe journal missing")

    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Probe journal unreadable") from exc

    if (
        type(payload) is not dict
        or payload.get("version") != 1
        or type(payload.get("attempts")) is not list
    ):
        raise ValueError("Invalid probe journal structure")

    attempts = payload["attempts"]

    for item in attempts:
        if (
            type(item) is not dict
            or item.get("status") not in STATUSES
            or not isinstance(item.get("started_at"), str)
        ):
            raise ValueError("Malformed probe record")

        try:
            stamp = datetime.fromisoformat(item["started_at"])
        except ValueError as exc:
            raise ValueError("Malformed probe timestamp") from exc

        if stamp.tzinfo is None:
            raise ValueError("Naive probe timestamp")

    return attempts


def diagnose(path=PROBE):
    attempts = load_probe(path)
    counts = Counter(a["status"] for a in attempts)
    latest = attempts[-1] if attempts else None

    # Deliberately omit API keys, request URLs and raw exceptions.
    return {
        "total_attempts": len(attempts),
        "verified_count": counts["VERIFIED"],
        "uncertain_count": counts["UNCERTAIN"],
        "latest_status": (
            latest["status"] if latest else "NONE"
        ),
        "latest_started_at": (
            latest["started_at"] if latest else None
        ),
        "new_api_request_allowed_by_this_script": False,
        "journal_modified": False,
        "recovery_decision": (
            "MANUAL_REVIEW_REQUIRED"
            if latest and latest["status"] != "VERIFIED"
            else "NO_UNRESOLVED_LATEST_ATTEMPT"
        ),
    }


@contextmanager
def archive_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".archive.lock"

    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write(path, content):
    """Write a new file atomically without overwriting old evidence."""
    path = Path(path)
    temp = None

    if path.exists():
        raise ValueError("Archive entry already exists")

    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent,
            prefix=".stage40_", delete=False
        ) as handle:
            temp = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if path.exists():
            raise ValueError("Concurrent archive entry detected")

        # Protected by archive lock for cooperating Stage 40 writers.
        os.replace(temp, path)

    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def collect(source=SOURCE, directory=ARCHIVE, *,
            probe=PROBE, now=None):
    """Archive local bytes; never certify provider or broker provenance."""
    # Reject malformed journal, but permit quarantining when unresolved.
    diagnostic = diagnose(probe)

    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError("Timezone-aware collection time required")

    source = Path(source)
    directory = Path(directory)

    if not source.is_file():
        raise ValueError("Source CSV unavailable")

    with archive_lock(directory):
        raw = source.read_bytes()

        if not raw:
            raise ValueError("Empty snapshot cannot be archived")

        digest = hashlib.sha256(raw).hexdigest()
        csv_path = directory / f"{digest}.csv"
        meta_path = directory / f"{digest}.json"

        if csv_path.exists():
            if hashlib.sha256(csv_path.read_bytes()).hexdigest() != digest:
                raise ValueError("Archived CSV hash mismatch")
        else:
            atomic_write(csv_path, raw)

        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf8"))
            if (
                metadata.get("sha256") != digest
                or metadata.get("status") != "QUARANTINED"
            ):
                raise ValueError("Existing metadata inconsistent")
            duplicate = True
        else:
            metadata = {
                "version": 1,
                "sha256": digest,
                "bytes": len(raw),
                "archived_at_utc": now.astimezone(timezone.utc).isoformat(),
                "status": "QUARANTINED",
                "source_type": "LOCAL_CSV",
                "provider_attested": False,
                "feed_mode_verified": False,
                "broker_parity_verified": False,
                "directional_signals_allowed": False,
                "analysis_only": True,
                "execution_enabled": False,
                "probe_status_at_collection": diagnostic["latest_status"],
            }
            atomic_write(
                meta_path,
                json.dumps(metadata, sort_keys=True, indent=2).encode()
            )
            duplicate = False

        return {
            "status": "QUARANTINED",
            "duplicate": duplicate,
            "sha256": digest,
            "csv_path": str(csv_path),
            "metadata_path": str(meta_path),
            "provider_attested": False,
            "directional_signals_allowed": False,
            "execution_enabled": False,
        }


def report(directory=ARCHIVE):
    directory = Path(directory)
    if not directory.exists():
        return {"snapshots": 0, "intact": 0, "corrupted": 0,
                "verified_live_snapshots": 0}

    snapshots = intact = corrupted = 0

    for meta_path in directory.glob("*.json"):
        snapshots += 1
        try:
            entry = json.loads(meta_path.read_text(encoding="utf8"))
            digest = entry["sha256"]

            if meta_path.stem != digest:
                raise ValueError("Manifest name mismatch")

            csv_path = directory / f"{digest}.csv"
            actual = hashlib.sha256(csv_path.read_bytes()).hexdigest()

            if (
                actual != digest
                or entry["status"] != "QUARANTINED"
                or entry["provider_attested"] is not False
                or entry["execution_enabled"] is not False
            ):
                raise ValueError("Invalid archive evidence")

            intact += 1
        except (OSError, ValueError, KeyError, TypeError):
            corrupted += 1

    return {
        "snapshots": snapshots,
        "intact": intact,
        "corrupted": corrupted,
        "verified_live_snapshots": 0,
        "analysis_only": True,
        "execution_enabled": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "action", choices=("diagnose", "collect", "report")
    )
    p.add_argument("--probe", type=Path, default=PROBE)
    p.add_argument("--csv", type=Path, default=SOURCE)
    p.add_argument("--archive", type=Path, default=ARCHIVE)
    args = p.parse_args()

    try:
        if args.action == "diagnose":
            result = diagnose(args.probe)
        elif args.action == "collect":
            result = collect(
                args.csv, args.archive, probe=args.probe
            )
        else:
            result = report(args.archive)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(
            1,
            f"BLOCKED: {type(exc).__name__}. "
            "Manual review required; no API retry.\n"
        )

    print("=== STAGE 40 PROVIDER RECOVERY ===")
    print(json.dumps(result, indent=2))
    print("API requests: 0")
    print("Order execution: DISABLED")
    print("Provider journal unchanged.")


if __name__ == "__main__":
    main()
