"""Explicitly approved, single-request Twelve Data /api_usage bootstrap.

This is a NEW request, not a retry or reconciliation of historical timeouts.
A stale snapshot is not reused as permission to fetch candles. The independent
/api_usage response becomes current evidence only after validation and an
audited budget reservation. Every attempted request remains in immutable
history; no automatic retry, refund, trade or background polling.
"""
from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from market_data import twelve_data_client as td
from market_data.api_credit_monitor import CreditSnapshot, parse_credit_headers
from market_data.authorization_journal import create_intent, finalize_intent, journal_path_for
from market_data.authorization_ledger import transition_authorization
from market_data.provider_credit_state import DEFAULT_PATH, load_credit_state, save_credit_state
from market_data.recovery_authorization import check_recovery_accounting
from market_data.recovery_verified_gate import verified_recovery_override
from market_data.unified_request_guard import _load_ledger, _save_json_atomic

API_USAGE_URL = "https://api.twelvedata.com/api_usage"


class AccountUsageBootstrapBlocked(RuntimeError):
    pass


def _now(value=None):
    value = value or datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountUsageBootstrapBlocked("Aware UTC time required")
    return value.astimezone(timezone.utc)


def _journal(path):
    if not path.exists():
        return {"version": 1, "attempts": []}
    if path.is_symlink():
        raise AccountUsageBootstrapBlocked("Usage journal redirected")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AccountUsageBootstrapBlocked("Usage journal unreadable") from exc
    if (type(data) is not dict or data.get("version") != 1
            or type(data.get("attempts")) is not list):
        raise AccountUsageBootstrapBlocked("Usage journal invalid")
    for entry in data["attempts"]:
        if (type(entry) is not dict
                or entry.get("status") not in {
                    "RESERVING", "RESERVED", "REQUEST_ATTEMPTED",
                    "UNCERTAIN", "VERIFIED",
                }
                or type(entry.get("request_id")) is not str):
            raise AccountUsageBootstrapBlocked("Usage journal entry invalid")
    return data


def _usage(payload, headers, *, response_time):
    """Parse independently reported current usage; never extrapolate stale credit."""
    if type(payload) is not dict or payload.get("status") == "error":
        raise AccountUsageBootstrapBlocked("Provider usage response invalid")
    limit, used = payload.get("plan_limit"), payload.get("current_usage")
    if (type(limit) is not int or type(used) is not int
            or limit < 1 or not 0 <= used <= limit):
        raise AccountUsageBootstrapBlocked("Provider minute usage invalid")
    if payload.get("plan_category", "").lower() != "basic":
        raise AccountUsageBootstrapBlocked("Expected Basic account; manual plan review required")
    day, day_limit = payload.get("daily_usage"), payload.get("plan_daily_limit")
    if (type(day) is not int or type(day_limit) is not int
            or day_limit < 1 or not 0 <= day <= day_limit):
        raise AccountUsageBootstrapBlocked("Provider daily usage invalid")
    if limit > td.MINUTE_LIMIT or day_limit > td.DAY_LIMIT:
        raise AccountUsageBootstrapBlocked("Configured plan limits differ; manual review")

    timestamp = payload.get("timestamp")
    if type(timestamp) is not str:
        raise AccountUsageBootstrapBlocked("Provider timestamp missing")
    try:
        observed = datetime.fromisoformat(timestamp.replace(" ", "T"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        observed = observed.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise AccountUsageBootstrapBlocked("Provider timestamp invalid") from exc
    if abs((response_time - observed).total_seconds()) > 120:
        raise AccountUsageBootstrapBlocked("Provider usage response timestamp stale")

    # Headers are a useful independent cross-check when supplied.
    parsed = parse_credit_headers(headers)
    remaining = limit - used
    if (parsed.credits_left is not None and parsed.credits_left != remaining):
        raise AccountUsageBootstrapBlocked("Usage body and credit headers disagree")
    if (parsed.credits_used is not None and parsed.credits_used != used):
        raise AccountUsageBootstrapBlocked("Usage counter and credit headers disagree")
    return CreditSnapshot(
        credits_used=used, credits_left=remaining,
        low_credits=remaining < 20, information_available=True,
    )


def bootstrap_account_usage_once(
    *, approved=False, api_key=None, provider_path=DEFAULT_PATH,
    budget_path=td.STATE_PATH, old_probe_path=None, journal_path=None,
    now=None, session=None,
):
    """One audited, expressly approved /api_usage request. May use one credit.

    Old UNCERTAIN records remain untouched. Any unverified attempt requires
    manual investigation. A successful usage snapshot is NOT proof of the old
    timeout's outcome.
    """
    if approved is not True:
        raise AccountUsageBootstrapBlocked("Explicit single-request approval required")
    key = api_key if api_key is not None else os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise AccountUsageBootstrapBlocked("Twelve Data API key missing")

    instant = _now(now)
    provider = Path(provider_path)
    budget = Path(budget_path)
    old_probe = Path(old_probe_path) if old_probe_path else provider.parent / "approved_research_probe.json"
    usage_log = Path(journal_path) if journal_path else provider.parent / "account_usage_bootstrap.json"
    provider_lock = provider.with_name(provider.name + ".lock")
    probe_lock = old_probe.with_name(old_probe.name + ".lock")
    ledger_path = provider.with_name(provider.name + ".reservations.json")
    auth_journal = journal_path_for(provider)
    renewal_log = provider.parent / "verified_credit_renewals.json"
    recovery_marker = provider.with_name(provider.name + ".recovery_required.json")

    paths = (provider, budget, old_probe, usage_log, provider_lock, probe_lock,
             ledger_path, auth_journal, renewal_log, recovery_marker)
    if len({p.resolve() for p in paths}) != len(paths):
        raise AccountUsageBootstrapBlocked("Overlapping accounting paths")
    if usage_log.parent.resolve() != provider.parent.resolve():
        raise AccountUsageBootstrapBlocked("Usage journal must share provider directory")

    probe_lock.parent.mkdir(parents=True, exist_ok=True)
    with probe_lock.open("a+b") as probe_fd:
        fcntl.flock(probe_fd.fileno(), fcntl.LOCK_SH)
        try:
            if (os.fstat(probe_fd.fileno()).st_dev, os.fstat(probe_fd.fileno()).st_ino) != (
                os.stat(probe_lock).st_dev, os.stat(probe_lock).st_ino
            ):
                raise AccountUsageBootstrapBlocked("Old-probe lock changed")
            if not verified_recovery_override(old_probe):
                raise AccountUsageBootstrapBlocked("Verified independent recovery missing")

            provider.parent.mkdir(parents=True, exist_ok=True)
            with provider_lock.open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    if (os.fstat(lock.fileno()).st_dev, os.fstat(lock.fileno()).st_ino) != (
                        os.stat(provider_lock).st_dev, os.stat(provider_lock).st_ino
                    ):
                        raise AccountUsageBootstrapBlocked("Provider lock changed")
                    if recovery_marker.exists():
                        raise AccountUsageBootstrapBlocked("Authorization recovery marker unresolved")
                    check_recovery_accounting(provider)
                    # A snapshot later than this operation's clock is NOT
                    # expired data. Treat clock rollback/skew as a hard block:
                    # never authorize another request from a negative age.
                    if provider.exists():
                        try:
                            existing = json.loads(provider.read_text(encoding="utf-8"))
                            if type(existing) is not dict or existing.get("version") != 1:
                                raise ValueError("Invalid provider snapshot")
                            observed = datetime.fromisoformat(existing["observed_at"])
                            if observed.tzinfo is None or observed.utcoffset() is None:
                                raise ValueError("Naive provider timestamp")
                            if observed.astimezone(timezone.utc) > instant:
                                raise AccountUsageBootstrapBlocked(
                                    "Credit snapshot newer than evaluation clock; no request"
                                )
                        except (OSError, ValueError, TypeError, KeyError) as exc:
                            raise AccountUsageBootstrapBlocked(
                                "Provider credit evidence invalid; no request"
                            ) from exc
                    if load_credit_state(path=provider, now=instant) is not None:
                        raise AccountUsageBootstrapBlocked("Credit snapshot already fresh")
                    log = _journal(usage_log)
                    if any(a["status"] != "VERIFIED" for a in log["attempts"]):
                        raise AccountUsageBootstrapBlocked("Previous usage refresh unresolved; no retry")
                    if renewal_log.exists():
                        from market_data.verified_credit_renewal import _read_log
                        renewals = _read_log(renewal_log)
                        if any(a["status"] != "VERIFIED" for a in renewals["attempts"]):
                            raise AccountUsageBootstrapBlocked("Previous credit renewal unresolved")

                    ledger = _load_ledger(ledger_path)
                    request_id = uuid.uuid4().hex
                    if request_id in ledger["requests"]:
                        raise AccountUsageBootstrapBlocked("Request ID collision")
                    log["attempts"].append({
                        "request_id": request_id,
                        "status": "RESERVING",
                        "created_at_utc": instant.isoformat(),
                        "http_attempted": False,
                        "endpoint": "api_usage",
                        "analysis_only": True,
                    })
                    entry = log["attempts"][-1]
                    # Durable intent before local budget reservation; failures
                    # remain unresolved and cannot silently be repeated.
                    _save_json_atomic(usage_log, log)
                    create_intent(auth_journal, request_id=request_id,
                                  authorized_at=instant.isoformat(), credits=1)
                    td.reserve_request(path=budget, now=instant)
                    ledger["requests"][request_id] = {
                        "credits": 1, "status": "PENDING",
                        "authorized_at": instant.isoformat(),
                        "snapshot_observed_at": instant.isoformat(),
                    }
                    ledger["reserved"] += 1
                    _save_json_atomic(ledger_path, ledger)
                    finalize_intent(auth_journal, request_id)
                    entry["status"] = "RESERVED"
                    _save_json_atomic(usage_log, log)
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

            try:
                entry["http_attempted"] = True
                entry["status"] = "REQUEST_ATTEMPTED"
                _save_json_atomic(usage_log, log)

                client = session if session is not None else requests
                response = client.get(
                    API_USAGE_URL,
                    params={"format": "JSON", "timezone": "UTC"},
                    headers={"Authorization": "apikey " + key},
                    timeout=(5, 30), allow_redirects=False,
                )
                response.raise_for_status()
                if getattr(response, "status_code", None) != 200:
                    raise AccountUsageBootstrapBlocked("Provider usage HTTP status invalid")
                response_time = _now()
                snapshot = _usage(response.json(), response.headers, response_time=response_time)

                with provider_lock.open("a+b") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                    try:
                        # Never overwrite a newer concurrent trusted observation.
                        if provider.exists():
                            last = json.loads(provider.read_text(encoding="utf-8"))
                            last_at = _now(datetime.fromisoformat(last["observed_at"]))
                            if last_at > response_time:
                                raise AccountUsageBootstrapBlocked("Newer provider observation exists")
                        # Provider snapshot is persisted first. If a crash
                        # occurs before the VERIFIED journal checkpoint, the
                        # durable request remains uncertain, never retried.
                        save_credit_state(snapshot, path=provider, now=response_time)
                        entry.update({
                            "status": "VERIFIED",
                            "verified_at_utc": response_time.isoformat(),
                            "credits_left": snapshot.credits_left,
                            "credits_used": snapshot.credits_used,
                        })
                        _save_json_atomic(usage_log, log)
                    finally:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

                return {
                    "status": "VERIFIED",
                    "credits_left": snapshot.credits_left,
                    "current_usage": snapshot.credits_used,
                    "http_requests": 1,
                    "old_uncertain_unchanged": True,
                    "trading_enabled": False,
                }
            except BaseException:
                entry["status"] = "UNCERTAIN"
                try:
                    _save_json_atomic(usage_log, log)
                finally:
                    try:
                        transition_authorization(
                            provider_state_path=provider, request_id=request_id,
                            status="UNCERTAIN",
                        )
                    except Exception:
                        pass
                raise
        finally:
            fcntl.flock(probe_fd.fileno(), fcntl.LOCK_UN)
