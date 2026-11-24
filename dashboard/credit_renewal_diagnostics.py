"""Read-only, secret-free reasons for a blocked one-shot credit renewal.

No provider HTTP calls, budget mutation, or attempts to release reservations.
The actual authorization remains authoritative and rechecks every condition.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def credit_renewal_readiness(*, provider_path="data/api_usage/provider_credits.json", now=None):
    """Human-safe diagnostic, never authorization to call the API."""
    from market_data.basic8_credit_policy import PROVIDER_RESERVE_CREDITS
    from market_data.provider_credit_state import load_credit_state
    from market_data.recovery_verified_gate import verified_recovery_override
    from market_data.unified_request_guard import _load_ledger
    from market_data.minute_reservation_headroom import minute_pending_credits
    from market_data.verified_credit_renewal import MAX_EVIDENCE_AGE_SECONDS

    provider = Path(provider_path)
    old_probe = provider.parent / "approved_research_probe.json"
    renewal_log = provider.parent / "verified_credit_renewals.json"
    ledger_path = provider.with_name(provider.name + ".reservations.json")
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return {"status": "UNKNOWN", "reason": "Invalid diagnostic clock. No request attempted."}
    now = now.astimezone(timezone.utc)

    try:
        if not verified_recovery_override(old_probe):
            return {"status": "BLOCKED", "reason": "Verified Stage 52D recovery evidence is missing or invalid."}
        if renewal_log.exists():
            log = json.loads(renewal_log.read_text(encoding="utf-8"))
            if (type(log) is not dict or log.get("version") != 1 or type(log.get("attempts")) is not list):
                raise ValueError("Invalid renewal log")
            for attempt in log["attempts"]:
                if type(attempt) is not dict or attempt.get("status") not in {"RESERVING", "RESERVED", "REQUEST_ATTEMPTED", "VERIFIED", "UNCERTAIN"}:
                    raise ValueError("Invalid renewal record")
                if attempt["status"] != "VERIFIED":
                    return {"status": "BLOCKED", "reason": "A previous credit renewal is unresolved. Manual accounting review is required; do not retry."}
        if load_credit_state(path=provider, now=now) is not None:
            return {"status": "FRESH", "reason": "Provider snapshot is currently fresh; renewal is unnecessary. Normal fetch still requires authorization."}
        data = json.loads(provider.read_text(encoding="utf-8"))
        if type(data) is not dict or data.get("version") != 1:
            raise ValueError("Invalid provider snapshot")
        seen = datetime.fromisoformat(data["observed_at"])
        if seen.tzinfo is None or seen.utcoffset() is None:
            raise ValueError("Naive timestamp")
        age = (now - seen.astimezone(timezone.utc)).total_seconds()
        if age < 0 or age > MAX_EVIDENCE_AGE_SECONDS:
            return {"status": "BLOCKED", "reason": "Last authenticated provider credit observation is older than the renewal evidence limit."}
        ledger = _load_ledger(ledger_path)
        left = data.get("credits_left")
        reserved = ledger["reserved"]
        if type(left) is not int or type(reserved) is not int or reserved < 0:
            raise ValueError("Invalid credit counts")
        if left - minute_pending_credits(ledger, now=now, observed_at=seen) < 1 + PROVIDER_RESERVE_CREDITS:
            return {"status": "BLOCKED", "reason": "Conservative available credit headroom is insufficient after existing reservations; do not delete reservations."}
        return {"status": "POSSIBLE", "reason": "Preliminary credit checks pass; final budget and authorization guards can still block. No HTTP attempted."}
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return {"status": "UNKNOWN", "reason": "Credit state or accounting evidence could not be validated; preserve files for manual review."}
