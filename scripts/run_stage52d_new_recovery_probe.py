from market_data.recovery_authorization import check_recovery_accounting
"""Explicit one-shot recovery research probe.

Preserves historical UNCERTAIN journal.
Never retries automatically. No broker execution.
May consume one Twelve Data API credit when explicitly approved.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path

from scripts.approved_real_data_probe import probe_once, ProbeBlocked


ROOT = Path("data/api_usage")
REPORTS = Path("data/recovery_reports")

OLD = ROOT / "approved_research_probe.json"
CASE = REPORTS / "stage52d_20261119_uncertain_case.json"
ARCHIVE = REPORTS / "stage52d_historical_provider_credits.json"

CLAIM = ROOT / "stage52d_new_recovery_claim.json"
NEW_JOURNAL = ROOT / "stage52d_new_recovery_probe.json"

BUDGET = ROOT / "twelve_data_budget.json"
PROVIDER = ROOT / "provider_credits.json"
CSV = Path("data/real_market/stage52d_new_completed.csv")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_history():
    case = json.loads(CASE.read_text())
    original = json.loads(OLD.read_text())

    if (
        case.get("schema_version") != 1
        or case.get("classification") != "UNRESOLVED_ACCOUNTING"
        or type(original) is not dict
        or type(original.get("attempts")) is not list
        or not original["attempts"]
    ):
        raise ProbeBlocked("Recovery case invalid")

    if original["attempts"][-1].get("status") != "UNCERTAIN":
        raise ProbeBlocked("Expected old UNCERTAIN probe")

    if original["attempts"][-1].get("started_at") != case.get("probe_started_at"):
        raise ProbeBlocked("Old probe identity mismatch")

    expected = case.get("source_sha256")
    if type(expected) is not dict:
        raise ProbeBlocked("Missing recovery fingerprints")

    sources = {
        "probe": OLD,
        "execution": ROOT / "credit_refresh_execution.json",
        "lifecycle": ROOT / "credit_refresh_lifecycle.json",
        "provider": ARCHIVE,
    }

    for name, path in sources.items():
        if sha(path) != expected.get(name):
            raise ProbeBlocked("Historical evidence fingerprint mismatch")

    # Fail closed if current credits were manually changed before
    # this first recovery request.
    if sha(PROVIDER) != sha(ARCHIVE):
        raise ProbeBlocked("Current credit state already changed")

    if CLAIM.exists() or NEW_JOURNAL.exists():
        raise ProbeBlocked("Recovery already claimed or attempted")


def create_claim():
    CLAIM.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(
        CLAIM,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )

    with os.fdopen(fd, "w") as handle:
        json.dump({
            "version": 1,
            "status": "SINGLE_USE_CLAIMED",
            "purpose": "NEW_RECOVERY_RESEARCH_NOT_OLD_RETRY",
            "old_probe_sha256": sha(OLD),
            "http_may_be_attempted": True,
            "trading_enabled": False,
        }, handle)
        handle.flush()
        os.fsync(handle.fileno())

    directory = os.open(CLAIM.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def run(approved):
    if approved is not True:
        print("Recovery preview only. No HTTP request.")
        return

    if not os.environ.get("TWELVE_DATA_API_KEY"):
        raise ProbeBlocked("API key missing; no recovery attempted")

    lock_path = OLD.with_name(OLD.name + ".lock")

    # The original gate's stable lock prevents concurrent
    # normal fetches or old-probe modifications during recovery.
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            a = os.fstat(lock.fileno())
            b = os.stat(lock_path)

            if a.st_ino != b.st_ino or a.st_dev != b.st_dev:
                raise ProbeBlocked("Original probe lock changed")

            verify_history()
            check_recovery_accounting(PROVIDER)

            # Claim persists even if the process crashes afterward.
            create_claim()

            result = probe_once(
                approved=True,
                state_path=NEW_JOURNAL,
                budget_path=BUDGET,
                provider_path=PROVIDER,
                csv_path=CSV,
            )

            print("NEW REQUEST:", result["status"])
            print("CANDLES:", result["candles"])
            print("CREDITS LEFT:", result["credits_left"])
            print("CSV:", result["csv_path"])
            print("OLD REQUEST: UNCERTAIN (preserved)")
            print("TRADING: DISABLED")

        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approve-one-new-request",
        action="store_true",
        help="Explicitly allow ONE new provider request; may cost a credit",
    )
    args = parser.parse_args()

    try:
        run(args.approve_one_new_request)
    except Exception as exc:
        print("RECOVERY BLOCKED OR FAILED:", type(exc).__name__)
        print("No automatic retry. Inspect journals manually.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
