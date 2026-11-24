"""Offline, read-only classification of Twelve Data reservations.

Never releases reservations, refreshes timestamps, or contacts Twelve Data.
Does not print keys, URLs, response bodies, or private trading records.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_data.authorization_journal import journal_path_for, load_journal
from market_data.unified_request_guard import _load_ledger


def _load_json(path: Path):
    if not path.exists():
        return None
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"Invalid JSON object: {path.name}")
    return obj


def audit(provider: Path):
    provider = Path(provider)
    directory = provider.parent
    ledger_file = provider.with_name(provider.name + ".reservations.json")
    journal_file = journal_path_for(provider)
    if not ledger_file.exists() or not journal_file.exists():
        raise ValueError("Missing ledger or journal; no reconciliation is safe")
    ledger = _load_ledger(ledger_file)
    journal = load_journal(journal_file)
    requests = ledger["requests"]
    transactions = journal["transactions"]
    if set(requests) != set(transactions):
        raise ValueError("Journal and ledger request IDs disagree")
    if any(tx.get("status") != "FINALIZED" or tx.get("credits") != requests[rid]["credits"]
           for rid, tx in transactions.items()):
        raise ValueError("Unfinalized or inconsistent authorization evidence")

    verified = {}
    recovery = _load_json(directory / "stage52d_new_recovery_probe.json")
    if recovery and recovery.get("status") == "VERIFIED" and recovery.get("checkpoint") == "VERIFIED":
        rid = recovery.get("request_id")
        if isinstance(rid, str):
            verified[rid] = "stage52d_recovery_record"
    renewal = _load_json(directory / "verified_credit_renewals.json")
    if renewal:
        attempts = renewal.get("attempts")
        if not isinstance(attempts, list):
            raise ValueError("Invalid renewal attempt journal")
        for a in attempts:
            if not isinstance(a, dict):
                raise ValueError("Invalid renewal record")
            if a.get("status") == "VERIFIED" and isinstance(a.get("request_id"), str):
                verified[a["request_id"]] = "verified_credit_renewal_record"
    rows = []
    for rid, info in sorted(requests.items()):
        status = info["status"]
        evidence = verified.get(rid)
        if status == "SETTLED":
            classification = "ALREADY_SETTLED"
        elif status == "UNCERTAIN":
            classification = "UNRESOLVED_DO_NOT_RELEASE"
        elif evidence:
            classification = "REVIEW_VERIFIED_RECEIPT_NOT_AUTO_SETTLED"
        else:
            classification = "NO_BOUND_SUCCESS_RECEIPT_DO_NOT_RELEASE"
        rows.append({"id_prefix": rid[:10], "status": status, "credits": info["credits"],
                     "evidence": evidence or "none", "classification": classification})
    return {"schema": 1, "provider_snapshot_present": provider.exists(),
            "legacy_reserved": ledger["legacy_reserved"],
            "outstanding_reserved": ledger["reserved"], "request_count": len(rows),
            "requests": rows, "read_only": True, "safe_to_auto_release": False,
            "note": "A matching VERIFIED record is a review lead, not sufficient by itself to release a credit."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="data/api_usage/provider_credits.json")
    args = parser.parse_args()
    result = audit(Path(args.provider))
    print(json.dumps(result, indent=2))
    print("NO HTTP / NO RESERVATION CHANGES / NO BROKER ORDERS")


if __name__ == "__main__":
    main()
