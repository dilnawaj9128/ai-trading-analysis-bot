"""Explicit, audited Twelve Data snapshot renewal after VERIFIED Stage 52D recovery.

This is NOT a retry of the historical uncertain credit refresh. It makes a
separate new request only with explicit approval. Neither this module nor its
caller makes a background request or settles existing reservations.

A stale provider observation is used ONLY as a conservative upper bound for
*one explicitly approved* renewal; it is never represented as fresh. Any
uncertain renewal blocks future renewals until human reconciliation.
"""
import fcntl
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from config.market_config import create_research_config
from market_data import twelve_data_client as td
from market_data.authorization_journal import create_intent, finalize_intent, journal_path_for
from market_data.authorization_ledger import transition_authorization
from market_data.basic8_credit_policy import PROVIDER_RESERVE_CREDITS
from market_data.credit_response_handler import refresh_credits_from_response
from market_data.provider_credit_state import DEFAULT_PATH, load_credit_state
from market_data.recovery_authorization import check_recovery_accounting
from market_data.recovery_verified_gate import verified_recovery_override
from market_data.twelve_data_client import STATE_PATH, reserve_request
from market_data.unified_request_guard import _load_ledger, _save_json_atomic
from market_data.minute_reservation_headroom import minute_pending_credits


class VerifiedCreditRenewalBlocked(RuntimeError):
    pass


# Maximum age of the LAST VERIFIED credit header used as a bounded ceiling.
# This does NOT extend freshness for normal fetch. After 24h, fail closed.
MAX_EVIDENCE_AGE_SECONDS = 24 * 3600


def _utc(now=None):
    now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise VerifiedCreditRenewalBlocked("Timezone-aware timestamp required")
    return now.astimezone(timezone.utc)


def _read_log(path):
    if not path.exists():
        return {"version": 1, "attempts": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (type(data) is not dict or data.get("version") != 1
            or type(data.get("attempts")) is not list):
        raise VerifiedCreditRenewalBlocked("Invalid renewal journal")
    for attempt in data["attempts"]:
        if (type(attempt) is not dict
                or attempt.get("status") not in {"RESERVING", "RESERVED", "REQUEST_ATTEMPTED", "VERIFIED", "UNCERTAIN"}
                or type(attempt.get("request_id")) is not str):
            raise VerifiedCreditRenewalBlocked("Invalid renewal journal entry")
    return data


def _save_log(path, log):
    path.parent.mkdir(parents=True, exist_ok=True)
    _save_json_atomic(path, log)


def renew_verified_credits_once(
    *, approved=False, api_key=None, provider_path=DEFAULT_PATH,
    budget_path=STATE_PATH, old_probe_path=None, journal_path=None,
    now=None, session=None,
):
    """One *new* EUR/USD request. Never retries a prior renewal attempt.

    Raises before HTTP on missing approval/key, invalid attestation, fresh
    snapshot, exhausted budget/headroom, or uncertain prior renewal.
    """
    if approved is not True:
        raise VerifiedCreditRenewalBlocked("Explicit one-new-request approval required")
    key = api_key if api_key is not None else os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise VerifiedCreditRenewalBlocked("Twelve Data API key missing")
    now = _utc(now)
    provider = Path(provider_path)
    budget = Path(budget_path)
    old_probe = Path(old_probe_path) if old_probe_path is not None else provider.parent / "approved_research_probe.json"
    renew_log = Path(journal_path) if journal_path is not None else provider.parent / "verified_credit_renewals.json"
    ledger_path = provider.with_name(provider.name + ".reservations.json")
    auth_journal = journal_path_for(provider)
    provider_lock = provider.with_name(provider.name + ".lock")
    probe_lock = old_probe.with_name(old_probe.name + ".lock")
    paths = [provider, budget, old_probe, renew_log, ledger_path, auth_journal, provider_lock, probe_lock]
    if len({p.resolve() for p in paths}) != len(paths):
        raise VerifiedCreditRenewalBlocked("Overlapping state paths")
    if renew_log.parent.resolve() != provider.parent.resolve():
        raise VerifiedCreditRenewalBlocked("Renewal journal must be beside provider state")

    # Hold the SAME stable probe lock used by normal fetch throughout this
    # operation. Prevent concurrent historical probe changes.
    probe_lock.parent.mkdir(parents=True, exist_ok=True)
    with probe_lock.open("a+b") as probe_file:
        fcntl.flock(probe_file.fileno(), fcntl.LOCK_SH)
        try:
            a, b = os.fstat(probe_file.fileno()), os.stat(probe_lock)
            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                raise VerifiedCreditRenewalBlocked("Probe lock changed")
            if not verified_recovery_override(old_probe):
                raise VerifiedCreditRenewalBlocked("Verified recovery attestation unavailable")

            provider.parent.mkdir(parents=True, exist_ok=True)
            with provider_lock.open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    a, b = os.fstat(lock.fileno()), os.stat(provider_lock)
                    if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                        raise VerifiedCreditRenewalBlocked("Provider lock changed")
                    check_recovery_accounting(provider)
                    log = _read_log(renew_log)
                    if any(a["status"] != "VERIFIED" for a in log["attempts"]):
                        raise VerifiedCreditRenewalBlocked("Prior renewal unresolved; manual review required")
                    if load_credit_state(path=provider, now=now) is not None:
                        raise VerifiedCreditRenewalBlocked("Provider snapshot already fresh")

                    evidence = json.loads(provider.read_text(encoding="utf-8"))
                    if type(evidence) is not dict or evidence.get("version") != 1:
                        raise VerifiedCreditRenewalBlocked("Invalid provider evidence")
                    observed = _utc(datetime.fromisoformat(evidence["observed_at"]))
                    age = (now - observed).total_seconds()
                    if age < 0 or age > MAX_EVIDENCE_AGE_SECONDS:
                        raise VerifiedCreditRenewalBlocked("Last verified credit evidence too old")
                    last_left = evidence.get("credits_left")
                    ledger = _load_ledger(ledger_path)
                    if (type(last_left) is not int or
                            last_left - minute_pending_credits(ledger, now=now, observed_at=observed) < 1 + PROVIDER_RESERVE_CREDITS):
                        raise VerifiedCreditRenewalBlocked("Insufficient conservative credit headroom")

                    request_id = uuid.uuid4().hex
                    entry = {
                        "request_id": request_id, "status": "RESERVING",
                        "created_at_utc": now.isoformat(),
                        "source_observed_at": observed.isoformat(),
                        "http_attempted": False, "analysis_only": True,
                    }
                    log["attempts"].append(entry)
                    # Durable intent BEFORE local budget mutation. Interrupted
                    # attempt blocks future renewals, never silent replay.
                    _save_log(renew_log, log)
                    create_intent(auth_journal, request_id=request_id,
                                  authorized_at=now.isoformat(), credits=1)
                    reserve_request(path=budget, now=now)
                    ledger["requests"][request_id] = {
                        "credits": 1, "status": "PENDING",
                        "authorized_at": now.isoformat(),
                        "snapshot_observed_at": observed.isoformat(),
                    }
                    ledger["reserved"] += 1
                    _save_json_atomic(ledger_path, ledger)
                    finalize_intent(auth_journal, request_id)
                    entry["status"] = "RESERVED"
                    _save_log(renew_log, log)
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

            try:
                # Persist request-attempt state before transport.
                entry["status"] = "REQUEST_ATTEMPTED"
                entry["http_attempted"] = True
                _save_log(renew_log, log)
                client = session if session is not None else requests
                response = client.get(
                    td.API_URL,
                    params={"apikey": key, "symbol": "EUR/USD", "interval": "1min",
                            "outputsize": td.MAX_CANDLES, "timezone": "UTC", "format": "JSON"},
                    timeout=(5, 30), allow_redirects=False,
                )
                response.raise_for_status()
                if getattr(response, "status_code", None) != 200:
                    raise VerifiedCreditRenewalBlocked("Unexpected HTTP status")
                config = create_research_config("quotex", "forex", "EUR/USD", "1min", 15)
                candles = td.parse_candles(response.json(), config, now=_utc())
                refresh = refresh_credits_from_response(response, path=provider, now=_utc())
                if refresh.updated is not True or refresh.credits_left is None:
                    raise VerifiedCreditRenewalBlocked("Provider credit headers missing")
                entry.update(status="VERIFIED", verified_at_utc=_utc().isoformat(),
                             credits_left=refresh.credits_left, candles=candles["candles"])
                _save_log(renew_log, log)
                return {
                    "status": "VERIFIED", "request_id": request_id,
                    "credits_left": refresh.credits_left,
                    "candles": candles["candles"], "http_requests": 1,
                    "old_uncertain_unchanged": True, "analysis_only": True,
                }
            except BaseException:
                entry["status"] = "UNCERTAIN"
                try:
                    _save_log(renew_log, log)
                finally:
                    try:
                        transition_authorization(provider_state_path=provider,
                                                 request_id=request_id, status="UNCERTAIN")
                    except Exception:
                        pass
                raise
        finally:
            fcntl.flock(probe_file.fileno(), fcntl.LOCK_UN)
