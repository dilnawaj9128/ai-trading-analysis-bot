"""Stage 52D Part 3: offline, evidence-bound recovery case.

Never executes HTTP, settles requests, or authorizes retries.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from market_data.uncertain_recovery import (
    RecoveryEvidenceError,
    assess_recovery,
)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_case(root):
    root = Path(root)

    sources = {
        "probe": root / "approved_research_probe.json",
        "execution": root / "credit_refresh_execution.json",
        "lifecycle": root / "credit_refresh_lifecycle.json",
        "provider": root / "provider_credits.json",
    }

    assessment = assess_recovery(
        probe_path=sources["probe"],
        execution_path=sources["execution"],
        lifecycle_path=sources["lifecycle"],
        provider_path=sources["provider"],
    )

    if assessment["probe_status"] != "UNCERTAIN":
        raise RecoveryEvidenceError(
            "This case requires an unresolved probe"
        )

    fingerprints = {
        name: sha256_file(path)
        for name, path in sources.items()
    }

    return {
        "schema_version": 1,
        "case_type": "PROBE_AND_CREDIT_ACCOUNTING_REVIEW",
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "classification": "UNRESOLVED_ACCOUNTING",
        "probe_started_at": assessment["probe_started_at"],
        "probe_status": assessment["probe_status"],
        "probe_attempt_count": assessment["probe_attempts"],
        "refresh_execution_status":
            assessment["refresh_execution_status"],
        "refresh_lifecycle_status":
            assessment["refresh_lifecycle_status"],
        "source_sha256": fingerprints,
        "provider_observation": {
            "source": "USER_SUPPLIED_TWELVE_DATA_SCREENSHOTS",
            "report_date": "2026-11-19",
            "aggregate_api_credits_used": 1,
            "displayed_usage_hour": "APPROX_13_00",
            "chart_timezone_verified": False,
            "request_specific_match": False,
            "http_success_proven": False,
        },
        "decision": {
            "old_request_verified": False,
            "old_request_outcome": "UNKNOWN",
            "provider_usage_attribution": "UNPROVEN",
            "fresh_credit_snapshot_available": False,
            "new_api_request_authorized": False,
            "retry_allowed": False,
            "trading_enabled": False,
            "manual_review_required": True,
        },
    }


def save_case_exclusive(case, destination):
    """Create a new evidence file; never replace an existing case."""
    destination = Path(destination)
    destination.parent.mkdir(
        parents=True, exist_ok=True
    )

    data = (
        json.dumps(case, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    fd = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )

    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())

    directory = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

    return destination
