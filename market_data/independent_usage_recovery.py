"""One independently accounted fresh /api_usage snapshot after an old uncertain renewal.

This is a NEW request, NEVER a retry of an old request. The old UNCERTAIN
renewal and older receipt-less holds remain in the immutable ledger.
A returned account-wide usage summary NEVER settles an older request.
A new failed request is UNCERTAIN and blocks any replay.
"""
from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from market_data.account_usage_bootstrap import _usage, API_USAGE_URL
from market_data.authorization_journal import (
    create_intent, finalize_intent, journal_path_for,
)
from market_data.provider_credit_state import (
    DEFAULT_PATH, load_credit_state, save_credit_state,
)
from market_data.recovery_authorization import check_recovery_accounting
from market_data.recovery_verified_gate import verified_recovery_override
from market_data.unified_request_guard import _load_ledger, _save_json_atomic
from market_data.twelve_data_client import STATE_PATH, reserve_request
from market_data.verified_reservation_settlement import (
    _settle_locked, _digest, _read, _receipt_path,
)
from market_data.authorization_ledger import transition_authorization


class IndependentRecoveryBlocked(RuntimeError):
    pass


JOURNAL_NAME = "independent_usage_recovery.json"
SOURCE_NAME = "INDEPENDENT_USAGE_RECOVERY"


def _utc(now=None):
    clock = now or datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        raise IndependentRecoveryBlocked("UTC-aware clock required")
    return clock.astimezone(timezone.utc)


def _load_log(path):
    if not path.exists():
        return {"version": 1, "attempts": []}
    if path.is_symlink():
        raise IndependentRecoveryBlocked("Recovery journal symlink not allowed")
    log = _read(path)
    if log.get("version") != 1 or type(log.get("attempts")) is not list:
        raise IndependentRecoveryBlocked("Invalid independent recovery journal")
    for e in log["attempts"]:
        if type(e) is not dict or type(e.get("request_id")) is not str:
            raise IndependentRecoveryBlocked("Invalid independent recovery entry")
        if e.get("status") not in ("RESERVING", "RESERVED", "REQUEST_ATTEMPTED", "VERIFIED", "UNCERTAIN"):
            raise IndependentRecoveryBlocked("Invalid independent recovery status")
    return log


def verified_independent_recovery(*, provider_path=DEFAULT_PATH, now=None):
    """Independent proof only for operational freshness, NEVER old outcomes."""
    provider = Path(provider_path)
    try:
        log = _load_log(provider.parent / JOURNAL_NAME)
        candidates = [e for e in log["attempts"] if e["status"] == "VERIFIED"]
        if not candidates or any(e["status"] != "VERIFIED" for e in log["attempts"]):
            return False
        latest = candidates[-1]
        rid = latest["request_id"]
        receipt = _read(_receipt_path(provider, rid))
        if not (receipt.get("version") == 1
                and receipt.get("request_id") == rid
                and receipt.get("source") == SOURCE_NAME
                and receipt.get("credits") == 1
                and receipt.get("evidence_sha256") == _digest(latest)):
            return False
        ledger = _load_ledger(provider.with_name(provider.name + ".reservations.json"))
        if ledger["requests"][rid]["status"] != "SETTLED":
            return False
        credit = load_credit_state(path=provider, now=_utc(now))
        if credit is None:
            return False
        state = _read(provider)
        when = datetime.fromisoformat(state["observed_at"])
        if when.tzinfo is None:
            return False
        verified_at = datetime.fromisoformat(latest["verified_at_utc"])
        if verified_at.tzinfo is None:
            return False
        if when.astimezone(timezone.utc) < verified_at.astimezone(timezone.utc):
            return False
        renewal = provider.parent / "verified_credit_renewals.json"
        if renewal.exists():
            old = _read(renewal)
            for entry in old.get("attempts", []):
                if entry.get("status") != "VERIFIED":
                    timestamp = datetime.fromisoformat(entry["created_at_utc"])
                    if timestamp.tzinfo is None or timestamp >= verified_at:
                        return False
        return True
    except (OSError, ValueError, KeyError, TypeError, IndependentRecoveryBlocked):
        return False


def recover_once(*, approved=False, api_key=None, provider_path=DEFAULT_PATH,
                 budget_path=STATE_PATH, now=None, session=None):
    """One distinct request, documented and accounted; no retries."""
    if approved is not True:
        raise IndependentRecoveryBlocked("Explicit approval for one new credit-consuming request required")
    if not api_key:
        raise IndependentRecoveryBlocked("Missing API key")
    clock = _utc(now)
    provider = Path(provider_path)
    root = provider.parent
    log_path = root / JOURNAL_NAME
    lock_path = provider.with_name(provider.name + ".lock")
    probe = root / "approved_research_probe.json"
    probe_lock_path = probe.with_name(probe.name + ".lock")
    ledger_path = provider.with_name(provider.name + ".reservations.json")
    paths = [provider, budget_path, log_path, lock_path, probe, probe_lock_path, ledger_path, journal_path_for(provider)]
    if len({Path(p).resolve() for p in paths}) != len(paths):
        raise IndependentRecoveryBlocked("Overlapping state paths")

    probe_lock_path.parent.mkdir(parents=True, exist_ok=True)
    with probe_lock_path.open("a+b") as probe_lock:
        fcntl.flock(probe_lock.fileno(), fcntl.LOCK_SH)
        if (os.fstat(probe_lock.fileno()).st_dev, os.fstat(probe_lock.fileno()).st_ino) != (
            os.stat(probe_lock_path).st_dev, os.stat(probe_lock_path).st_ino
        ):
            raise IndependentRecoveryBlocked("Probe lock identity changed")
        if not verified_recovery_override(probe):
            raise IndependentRecoveryBlocked("Earlier recovery integrity not verified")
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if (os.fstat(lock.fileno()).st_dev, os.fstat(lock.fileno()).st_ino) != (
                os.stat(lock_path).st_dev, os.stat(lock_path).st_ino
            ):
                raise IndependentRecoveryBlocked("Provider lock identity changed")
            check_recovery_accounting(provider)
            if load_credit_state(path=provider, now=clock) is not None:
                return {"status": "SNAPSHOT_ALREADY_FRESH", "new_http_requests": 0}
            log = _load_log(log_path)
            if any(e["status"] != "VERIFIED" for e in log["attempts"]):
                raise IndependentRecoveryBlocked("Earlier independent recovery unresolved; do not retry")
            ledger = _load_ledger(ledger_path)
            # Existing uncertain request remains intact; old holds are not
            # equivalent to current-minute consumption.
            if any(e["status"] == "UNCERTAIN"
                   and datetime.fromisoformat(e["authorized_at"]).astimezone(timezone.utc).replace(second=0, microsecond=0)
                       == clock.replace(second=0, microsecond=0)
                   for e in ledger["requests"].values()):
                raise IndependentRecoveryBlocked("Uncertain request exists in current UTC minute")
            rid = uuid.uuid4().hex
            entry = {
                "request_id": rid, "status": "RESERVING",
                "created_at_utc": clock.isoformat(),
                "http_attempted": False, "endpoint": "api_usage",
            }
            log["attempts"].append(entry)
            _save_json_atomic(log_path, log)
            create_intent(journal_path_for(provider), request_id=rid, authorized_at=clock.isoformat(), credits=1)
            reserve_request(path=Path(budget_path), now=clock)
            ledger["requests"][rid] = {
                "credits": 1, "status": "PENDING",
                "authorized_at": clock.isoformat(),
                "snapshot_observed_at": clock.isoformat(),
            }
            ledger["reserved"] += 1
            _save_json_atomic(ledger_path, ledger)
            finalize_intent(journal_path_for(provider), rid)
            entry["status"] = "RESERVED"
            _save_json_atomic(log_path, log)

        try:
            entry["http_attempted"] = True
            entry["status"] = "REQUEST_ATTEMPTED"
            _save_json_atomic(log_path, log)
            client = session or requests
            response = client.get(
                API_USAGE_URL,
                params={"format": "JSON", "timezone": "UTC"},
                headers={"Authorization": "apikey " + api_key},
                timeout=(5, 30), allow_redirects=False,
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise IndependentRecoveryBlocked("Unexpected usage HTTP status")
            verified_at = _utc()
            snapshot = _usage(response.json(), response.headers, response_time=verified_at)
            with lock_path.open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                check_recovery_accounting(provider)
                if provider.exists():
                    original = _read(provider)
                    last_at = datetime.fromisoformat(original["observed_at"])
                    if last_at.tzinfo is None or last_at > verified_at:
                        raise IndependentRecoveryBlocked("Provider snapshot newer than response")
                save_credit_state(snapshot, path=provider, now=verified_at)
                entry.update(
                    status="VERIFIED", verified_at_utc=verified_at.isoformat(),
                    credits_left=snapshot.credits_left, credits_used=snapshot.credits_used,
                )
                _save_json_atomic(log_path, log)
                # This settles ONLY the new request bound to this authenticated
                # response, never one of the historical 19 holds.
                _settle_locked(provider, rid, SOURCE_NAME, _digest(entry))
            return {
                "status": "VERIFIED_NEW_USAGE_ONLY",
                "new_http_requests": 1, "request_id_prefix": rid[:10],
                "provider_credits_left_at_receipt": snapshot.credits_left,
                "historical_uncertain_unchanged": True, "old_requests_settled": 0,
            }
        except BaseException:
            entry["status"] = "UNCERTAIN"
            try:
                _save_json_atomic(log_path, log)
            finally:
                try:
                    transition_authorization(
                        provider_state_path=provider, request_id=rid, status="UNCERTAIN"
                    )
                except Exception:
                    pass
            raise
