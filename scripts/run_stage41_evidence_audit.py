"""Stage 41: offline provider evidence and recovery audit.

No HTTP, API retries, journal mutation, or trading operations.
Local evidence cannot independently certify broker/feed parity.
"""

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROBE = Path("data/api_usage/approved_research_probe.json")
CSV = Path("data/real_market/latest_eurusd_completed.csv")
OUT = Path("data/recovery/stage41")

STATUSES = {
    "INTENT", "BUDGET_RESERVED",
    "REQUEST_ATTEMPTED", "VERIFIED", "UNCERTAIN",
}


def utc(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return stamp.astimezone(timezone.utc)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        while chunk := file.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_probe(path):
    payload = json.loads(Path(path).read_text(encoding="utf8"))

    if (
        type(payload) is not dict
        or payload.get("version") != 1
        or type(payload.get("attempts")) is not list
    ):
        raise ValueError("Invalid probe journal")

    for attempt in payload["attempts"]:
        if (
            type(attempt) is not dict
            or attempt.get("status") not in STATUSES
            or not isinstance(attempt.get("started_at"), str)
        ):
            raise ValueError("Invalid probe attempt")

        utc(attempt["started_at"])

    return payload["attempts"]


def audit(*, probe=PROBE, csv=CSV):
    """Return sanitized evidence statuses only, no secrets."""

    attempts = load_probe(probe)
    csv_path = Path(csv).resolve()
    csv_digest = (
        sha256_file(csv_path) if csv_path.is_file() else None
    )

    summaries = []

    for index, attempt in enumerate(attempts, 1):
        status = attempt["status"]
        reason = "NOT_VERIFIED"

        if status == "UNCERTAIN":
            reason = "UNRESOLVED_REQUEST"

        elif status == "VERIFIED":
            digest = attempt.get("csv_sha256")

            if not isinstance(digest, str) or not re.fullmatch(
                r"[0-9a-f]{64}", digest
            ):
                reason = "LEGACY_VERIFIED_NO_HASH"

            elif attempt.get("provider") != "twelve_data":
                reason = "PROVIDER_METADATA_UNVERIFIED"

            elif attempt.get("symbol") != "EUR/USD":
                reason = "SYMBOL_MISMATCH"

            elif attempt.get("timeframe") != "1min":
                reason = "TIMEFRAME_MISMATCH"

            elif attempt.get("csv_path") != str(csv_path):
                reason = "CSV_PATH_MISMATCH"

            elif csv_digest != digest:
                reason = "CSV_HASH_MISMATCH"

            else:
                reason = "LOCAL_HASH_MATCH"

        summaries.append({
            "attempt": index,
            "status": status,
            "started_at_utc": utc(
                attempt["started_at"]
            ).isoformat(),
            "evidence": reason,
        })

    latest = summaries[-1] if summaries else None
    unresolved = (
        latest is not None
        and latest["status"] != "VERIFIED"
    )

    # A matching local hash is not independent provider proof.
    # No automatically inferred live/delayed feed status.
    return {
        "stage": 41,
        "total_attempts": len(summaries),
        "attempts": summaries,
        "latest_status": (
            latest["status"] if latest else "NONE"
        ),
        "recovery_required": unresolved,
        "recovery_decision": (
            "MANUAL_REVIEW_REQUIRED"
            if unresolved else "REVIEW_EVIDENCE"
        ),
        "current_csv_sha256": csv_digest,
        "provider_feed_mode": "UNKNOWN",
        "broker_feed_parity_verified": False,
        "directional_analysis_authorized": False,
        "new_api_requests_authorized": False,
        "analysis_only": True,
        "execution_enabled": False,
    }


def write_evidence_report(report, directory=OUT):
    """Save a sanitized report without overwriting prior reports."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    raw = json.dumps(
        report, indent=2, sort_keys=True
    ).encode("utf8")

    digest = hashlib.sha256(raw).hexdigest()
    destination = directory / f"{digest}.json"

    if destination.exists():
        if destination.read_bytes() != raw:
            raise ValueError("Existing report corrupted")
        return destination, False

    temp = None

    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=directory,
            prefix=".evidence_", delete=False
        ) as handle:
            temp = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())

        # Atomic no-overwrite publication.
        try:
            os.link(temp, destination)
            created = True
        except FileExistsError:
            if destination.read_bytes() != raw:
                raise ValueError("Conflicting report")
            created = False

        return destination, created

    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("audit", "export")
    )
    parser.add_argument("--probe", type=Path, default=PROBE)
    parser.add_argument("--csv", type=Path, default=CSV)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    try:
        result = audit(probe=args.probe, csv=args.csv)

        print("=== STAGE 41 PROVIDER EVIDENCE AUDIT ===")
        print(json.dumps(result, indent=2))

        if args.action == "export":
            path, created = write_evidence_report(
                result, args.out
            )
            print("report_path:", path)
            print("new_report_created:", created)

    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(
            1,
            f"BLOCKED: {type(exc).__name__}. "
            "Evidence requires manual review.\n"
        )

    print("API requests: 0")
    print("Original journal: UNCHANGED")
    print("Trading execution: DISABLED")
    print("Feed mode: NOT VERIFIED")


if __name__ == "__main__":
    main()
