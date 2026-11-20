"""Single-shot EUR/USD recovery transport, separate from the old uncertain probe.

Uses the one-time recovery_transaction allocation ONCE. Never calls probe_once,
whose own reservation would double count. Research-only; no broker execution.

Caller must explicitly approve. A mockable session allows offline CI.
After ANY committed claim/transport failure the request is not retried.
"""
import fcntl
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from config.market_config import create_research_config
from market_data import twelve_data_client as td
from market_data.credit_response_handler import refresh_credits_from_response
from market_data.recovery_transaction import reserve_offline_recovery
from market_data.authorization_ledger import transition_authorization
from scripts.approved_real_data_probe import (
    _atomic_write, CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS,
)


class RecoveryTransportBlocked(RuntimeError):
    pass


def _utc(now=None):
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise RecoveryTransportBlocked("Timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def recover_once(
    *, approved=False, old_probe_path, case_path, archive_path,
    provider_path, budget_path, claim_path, recovery_journal_path, csv_path,
    api_key=None, session=None, now=None,
):
    """One separately approved API request, never an old-request retry."""
    if approved is not True:
        raise RecoveryTransportBlocked("Explicit one-new-request approval required")
    key = api_key if api_key is not None else os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise RecoveryTransportBlocked("API key missing")

    now = _utc(now)
    old_probe_path = Path(old_probe_path)
    recovery_journal_path = Path(recovery_journal_path)
    csv_path = Path(csv_path)
    provider_path = Path(provider_path)
    old_lock_path = old_probe_path.with_name(old_probe_path.name + ".lock")
    old_lock_path.parent.mkdir(parents=True, exist_ok=True)

    paths = [old_probe_path, recovery_journal_path, csv_path, provider_path,
             Path(claim_path), Path(case_path), Path(archive_path), Path(budget_path),
             old_lock_path]
    if len({p.resolve() for p in paths}) != len(paths):
        raise RecoveryTransportBlocked("Overlapping state paths")

    with old_lock_path.open("a+b") as old_lock:
        fcntl.flock(old_lock.fileno(), fcntl.LOCK_EX)
        try:
            a, b = os.fstat(old_lock.fileno()), os.stat(old_lock_path)
            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                raise RecoveryTransportBlocked("Old probe lock changed")
            if recovery_journal_path.exists():
                raise RecoveryTransportBlocked("Recovery journal already exists")

            # Claims and reserves under canonical provider lock, validating
            # immutable old evidence. Do not change the original probe.
            receipt = reserve_offline_recovery(
                provider_path=provider_path, budget_path=budget_path,
                claim_path=claim_path, case_path=case_path,
                archive_path=archive_path, old_probe_path=old_probe_path,
                explicitly_approved=True, now=now,
            )
            request_id = receipt["request_id"]
            journal = {
                "version": 1,
                "request_id": request_id,
                "status": "UNCERTAIN",
                "checkpoint": "BUDGET_RESERVED",
                "created_at_utc": now.isoformat(),
                "case_sha256": hashlib.sha256(Path(case_path).read_bytes()).hexdigest(),
                "old_probe_sha256": hashlib.sha256(old_probe_path.read_bytes()).hexdigest(),
                "http_attempted": False,
                "analysis_only": True,
                "trading_enabled": False,
            }
            recovery_journal_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(recovery_journal_path, journal)

            def checkpoint(value):
                journal["checkpoint"] = value
                _atomic_write(recovery_journal_path, journal)

            try:
                # Even process death between marking attempt and socket call
                # leaves the durable single-use claim, preventing replay.
                journal["http_attempted"] = True
                checkpoint("REQUEST_ATTEMPTED")
                client = session if session is not None else requests
                response = client.get(
                    td.API_URL,
                    params={
                        "apikey": key, "symbol": "EUR/USD",
                        "interval": "1min", "outputsize": 120,
                        "timezone": "UTC", "format": "JSON",
                    },
                    timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                    allow_redirects=False,
                )
                checkpoint("RESPONSE_RECEIVED")
                response.raise_for_status()
                if response.status_code != 200:
                    raise RecoveryTransportBlocked("Unexpected HTTP status")
                payload = response.json()
                config = create_research_config(
                    "quotex", "forex", "EUR/USD", "1min", 15
                )
                parsed = td.parse_candles(payload, config, now=_utc())
                checkpoint("CANDLES_VALIDATED")
                credits = refresh_credits_from_response(
                    response, path=provider_path, now=_utc()
                )
                if credits.updated is not True or credits.credits_left is None:
                    raise RecoveryTransportBlocked("Provider credit headers not verified")
                checkpoint("CREDITS_REFRESHED")

                csv_path.parent.mkdir(parents=True, exist_ok=True)
                temp = csv_path.with_name("." + csv_path.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    parsed["frame"].to_csv(temp, index=False)
                    os.replace(temp, csv_path)
                finally:
                    temp.unlink(missing_ok=True)
                sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
                journal.update({
                    "csv_sha256": sha,
                    "csv_path": str(csv_path.resolve()),
                    "candles": parsed["candles"],
                    "latest_utc": parsed["latest_utc"],
                    "credits_left": credits.credits_left,
                })
                checkpoint("CSV_PERSISTED")
                # The reservation is retained; this verified new response is
                # NOT evidence to settle the old or any other request.
                journal["status"] = "VERIFIED"
                journal["verified_at_utc"] = _utc().isoformat()
                checkpoint("VERIFIED")
                return {
                    "status": "VERIFIED",
                    "request_id": request_id,
                    "candles": parsed["candles"],
                    "credits_left": credits.credits_left,
                    "csv_path": str(csv_path),
                    "old_request_outcome": "UNKNOWN",
                    "http_requests": 1,
                    "analysis_only": True,
                }
            except BaseException:
                journal["status"] = "UNCERTAIN"
                # Never log raw exception strings: URLs may contain API keys.
                try:
                    checkpoint("FAILED_OR_UNKNOWN")
                finally:
                    try:
                        transition_authorization(
                            provider_state_path=provider_path,
                            request_id=request_id,
                            status="UNCERTAIN",
                        )
                    except Exception:
                        # Preserve both durable files for manual investigation.
                        pass
                raise
        finally:
            fcntl.flock(old_lock.fileno(), fcntl.LOCK_UN)
