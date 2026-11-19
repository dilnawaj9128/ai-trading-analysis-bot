"""Stage 52D: read-only uncertain-request reconciliation assessment.

Does not execute HTTP, change request state or authorize new requests.
"""

import hashlib
import json
from pathlib import Path


class RecoveryEvidenceError(RuntimeError):
    pass


def _load(path):
    path = Path(path)

    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise RecoveryEvidenceError(
            "Missing or invalid recovery evidence"
        ) from exc

    if not isinstance(data, dict):
        raise RecoveryEvidenceError("Invalid evidence structure")

    return data, hashlib.sha256(raw).hexdigest()


def assess_recovery(
    *,
    probe_path,
    execution_path,
    lifecycle_path,
    provider_path,
):
    probe, fingerprint = _load(probe_path)
    execution, _ = _load(execution_path)
    lifecycle, _ = _load(lifecycle_path)
    provider, _ = _load(provider_path)

    if probe.get("version") != 1:
        raise RecoveryEvidenceError("Unsupported probe version")

    attempts = probe.get("attempts")

    if not isinstance(attempts, list) or not attempts:
        raise RecoveryEvidenceError("No probe attempts")

    last = attempts[-1]

    if not isinstance(last, dict):
        raise RecoveryEvidenceError("Invalid probe attempt")

    status = last.get("status")

    if status not in {
        "INTENT", "BUDGET_RESERVED",
        "REQUEST_ATTEMPTED", "UNCERTAIN", "VERIFIED"
    }:
        raise RecoveryEvidenceError("Unknown probe status")

    execution_status = execution.get("status")
    lifecycle_status = lifecycle.get("status")

    if execution_status not in {
        "PREPARED", "RESERVATION_STARTED",
        "BUDGET_RESERVED", "REQUEST_ATTEMPTED",
        "UNCERTAIN"
    }:
        raise RecoveryEvidenceError("Invalid refresh execution status")

    if lifecycle_status not in {"CLAIMED", "ATTEMPTED"}:
        raise RecoveryEvidenceError("Invalid refresh lifecycle status")

    if status == "VERIFIED":
        classification = "PROBE_VERIFIED_SEPARATE_REFRESH_REVIEW"
    else:
        classification = "UNRESOLVED_ACCOUNTING"

    return {
        "version": 1,
        "classification": classification,
        "probe_status": status,
        "probe_attempts": len(attempts),
        "probe_started_at": last.get("started_at"),
        "probe_failure_category": last.get("failure_category"),
        "probe_journal_sha256": fingerprint,
        "refresh_execution_status": execution_status,
        "refresh_lifecycle_status": lifecycle_status,
        "provider_snapshot_observed_at": provider.get("observed_at"),
        "provider_credits_last_recorded": provider.get("credits_left"),
        "provider_dashboard_usage": "AGGREGATE_ONLY_NOT_REQUEST_PROOF",
        "historical_request_verified": status == "VERIFIED",
        "new_api_request_authorized": False,
        "retry_allowed": False,
        "trading_enabled": False,
    }
