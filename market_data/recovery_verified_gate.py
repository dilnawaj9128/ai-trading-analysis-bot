"""Strict attestation that a separate recovery request was VERIFIED.

Old fifth probe remains UNCERTAIN, with its immutable audit case. No HTTP.
A recovery signal never skips the independent credit/budget authorization gate.
"""
import hashlib
import json
from pathlib import Path

from market_data.authorization_journal import load_journal, journal_path_for
from market_data.unified_request_guard import _load_ledger


def _json(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError("Invalid recovery evidence")
    return payload


def verified_recovery_override(old_probe_path):
    """Fail closed: return False unless the exact recovery chain is verified."""
    old_probe_path = Path(old_probe_path)
    root = old_probe_path.parent
    if old_probe_path.name != "approved_research_probe.json":
        return False
    base = root.parent
    case_path = base / "recovery_reports" / "stage52d_20261119_uncertain_case.json"
    archive_path = base / "recovery_reports" / "stage52d_historical_provider_credits.json"
    claim_path = root / "recovery_txn_claim.json"
    recovery_path = root / "stage52d_new_recovery_probe.json"
    csv_path = base / "real_market" / "stage52d_new_completed.csv"
    provider_path = root / "provider_credits.json"

    try:
        case = _json(case_path)
        claim = _json(claim_path)
        recovery = _json(recovery_path)
        old = _json(old_probe_path)
        provider = _json(provider_path)
        if provider.get("version") != 1 or type(provider.get("credits_left")) is not int:
            return False

        if (case.get("schema_version") != 1
            or case.get("classification") != "UNRESOLVED_ACCOUNTING"
            or case.get("probe_status") != "UNCERTAIN"
            or type(old.get("attempts")) is not list or not old["attempts"]
            or old["attempts"][-1].get("status") != "UNCERTAIN"
            or old["attempts"][-1].get("started_at") != case.get("probe_started_at")):
            return False

        hashes = case.get("source_sha256")
        if type(hashes) is not dict:
            return False
        originals = {
            "probe": old_probe_path,
            "execution": root / "credit_refresh_execution.json",
            "lifecycle": root / "credit_refresh_lifecycle.json",
            "provider": archive_path,
        }
        if any(hashlib.sha256(p.read_bytes()).hexdigest() != hashes.get(k)
               for k, p in originals.items()):
            return False

        case_sha = hashlib.sha256(case_path.read_bytes()).hexdigest()
        old_sha = hashlib.sha256(old_probe_path.read_bytes()).hexdigest()
        request_id = claim.get("request_id")
        if (type(request_id) is not str or len(request_id) != 32
            or any(c not in "0123456789abcdef" for c in request_id)
            or claim.get("version") != 1
            or claim.get("case_sha256") != case_sha
            or claim.get("old_probe_sha256") != old_sha
            or claim.get("http_authorized") is not True
            or recovery.get("version") != 1
            or recovery.get("request_id") != request_id
            or recovery.get("case_sha256") != case_sha
            or recovery.get("old_probe_sha256") != old_sha
            or recovery.get("status") != "VERIFIED"
            or recovery.get("checkpoint") != "VERIFIED"
            or recovery.get("http_attempted") is not True
            or recovery.get("analysis_only") is not True
            or recovery.get("trading_enabled") is not False
            or type(recovery.get("candles")) is not int
            or recovery["candles"] < 1):
            return False

        if (Path(recovery.get("csv_path", "")).resolve() != csv_path.resolve()
            or hashlib.sha256(csv_path.read_bytes()).hexdigest()
                != recovery.get("csv_sha256")):
            return False

        journal = load_journal(journal_path_for(provider_path))
        ledger = _load_ledger(
            provider_path.with_name(provider_path.name + ".reservations.json")
        )
        tx = journal["transactions"].get(request_id)
        reservation = ledger["requests"].get(request_id)
        if (type(tx) is not dict or tx.get("status") != "FINALIZED"
            or tx.get("credits") != 1 or type(reservation) is not dict
            or reservation.get("credits") != 1
            or reservation.get("status") != "PENDING"
            or ledger["reserved"] < 1):
            return False

        return True
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return False
