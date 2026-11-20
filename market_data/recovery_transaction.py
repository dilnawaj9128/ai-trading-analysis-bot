"""Stage 52D: offline, single-use recovery authorization transaction.

This module NEVER authorizes HTTP. It durably accounts for a proposed
separate research request under the same provider lock, ledger, journal,
and local budget used by normal requests. Old UNCERTAIN evidence is untouched.

Any interrupted transaction leaves an INTENT / marker and FAILS CLOSED.
Never replay a claim or automatically refund a budget reservation.
"""
import fcntl
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from market_data.authorization_journal import (
    create_intent, finalize_intent, journal_path_for,
)
from market_data.recovery_authorization import (
    check_recovery_accounting, RecoveryAuthorizationBlocked,
)
from market_data.unified_request_guard import (
    _load_ledger, _save_json_atomic,
)
from market_data.twelve_data_client import reserve_request


class RecoveryTransactionBlocked(RuntimeError):
    pass


def _sync_parent(path):
    fd = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _exclusive_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(payload, file, sort_keys=True)
        file.flush()
        os.fsync(file.fileno())
    _sync_parent(path)


def reserve_offline_recovery(
    *, provider_path, budget_path, claim_path, case_path,
    archive_path, old_probe_path, explicitly_approved=False,
    now=None, reserve_credits=1, authorize_transport=False,
):
    """Reserve exactly one *local* request credit, never send HTTP.

    Returns an audit receipt with http_authorized=False. A subsequent
    network transport requires a separate reviewed implementation.
    """
    if explicitly_approved is not True:
        raise RecoveryTransactionBlocked("Explicit offline reservation approval required")
    if type(authorize_transport) is not bool:
        raise RecoveryTransactionBlocked("Invalid transport authorization")
    if type(reserve_credits) is not int or reserve_credits != 1:
        raise RecoveryTransactionBlocked("Invalid reserve policy")

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RecoveryTransactionBlocked("Timezone-aware timestamp required")
    now = now.astimezone(timezone.utc)

    provider_path = Path(provider_path)
    budget_path = Path(budget_path)
    claim_path = Path(claim_path)
    case_path = Path(case_path)
    archive_path = Path(archive_path)
    old_probe_path = Path(old_probe_path)
    ledger_path = provider_path.with_name(provider_path.name + ".reservations.json")
    journal_path = journal_path_for(provider_path)
    lock_path = provider_path.with_name(provider_path.name + ".lock")

    paths = [provider_path, budget_path, claim_path, case_path, archive_path,
             old_probe_path, ledger_path, journal_path, lock_path]
    if len({p.resolve() for p in paths}) != len(paths):
        raise RecoveryTransactionBlocked("Overlapping recovery paths")
    if claim_path.parent != provider_path.parent:
        raise RecoveryTransactionBlocked("Claim must share provider directory")

    provider_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            locked = os.fstat(lock.fileno())
            current = os.stat(lock_path)
            if (locked.st_dev, locked.st_ino) != (current.st_dev, current.st_ino):
                raise RecoveryTransactionBlocked("Provider lock replaced")
            # If any previous attempt started, do NOT retry, even if it crashed.
            if claim_path.exists():
                raise RecoveryTransactionBlocked("Recovery already claimed")

            from market_data.recovery_preflight import SOURCE_FILES
            try:
                case = json.loads(case_path.read_text(encoding="utf-8"))
                old = json.loads(old_probe_path.read_text(encoding="utf-8"))
                archive_bytes = archive_path.read_bytes()
                snapshot = json.loads(provider_path.read_text(encoding="utf-8"))
                budget = json.loads(budget_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as exc:
                raise RecoveryTransactionBlocked("Recovery evidence missing or corrupt") from exc

            if (type(case) is not dict or case.get("schema_version") != 1
                or case.get("classification") != "UNRESOLVED_ACCOUNTING"
                or case.get("probe_status") != "UNCERTAIN"
                or type(old) is not dict or old.get("version") != 1
                or type(old.get("attempts")) is not list or not old["attempts"]
                or old["attempts"][-1].get("status") != "UNCERTAIN"
                or old["attempts"][-1].get("started_at") != case.get("probe_started_at")
                or len(old["attempts"]) != case.get("probe_attempt_count")):
                raise RecoveryTransactionBlocked("Historical identity mismatch")
            decisions = case.get("decision")
            if (type(decisions) is not dict
                or decisions.get("old_request_verified") is not False
                or decisions.get("new_api_request_authorized") is not False
                or decisions.get("retry_allowed") is not False):
                raise RecoveryTransactionBlocked("Historical authorization state invalid")

            sources = {
                "probe": old_probe_path,
                "execution": provider_path.parent / SOURCE_FILES["execution"],
                "lifecycle": provider_path.parent / SOURCE_FILES["lifecycle"],
                "provider": archive_path,
            }
            hashes = case.get("source_sha256")
            if type(hashes) is not dict:
                raise RecoveryTransactionBlocked("Missing historical fingerprints")
            for name, source in sources.items():
                try:
                    actual = hashlib.sha256(source.read_bytes()).hexdigest()
                except OSError as exc:
                    raise RecoveryTransactionBlocked("Missing historical evidence") from exc
                if actual != hashes.get(name):
                    raise RecoveryTransactionBlocked("Historical fingerprint mismatch")
            if (provider_path.read_bytes() != archive_bytes
                or type(snapshot) is not dict or snapshot.get("version") != 1):
                raise RecoveryTransactionBlocked("Provider evidence changed")
            # Historical snapshot is ONLY a conservative budget ceiling, not
            # a fresh provider observation or authorization for HTTP.
            credits_left = snapshot.get("credits_left")
            if type(credits_left) is not int or credits_left < 2:
                raise RecoveryTransactionBlocked("Historical credits insufficient")

            if type(budget) is not dict:
                raise RecoveryTransactionBlocked("Budget state malformed")
            try:
                accounting = check_recovery_accounting(provider_path)
            except (RecoveryAuthorizationBlocked, ValueError) as exc:
                raise RecoveryTransactionBlocked("Existing authorization inconsistent") from exc
            ledger = _load_ledger(ledger_path)
            if credits_left - ledger["reserved"] < reserve_credits + 1:
                raise RecoveryTransactionBlocked("Insufficient historic credit headroom")

            request_id = uuid.uuid4().hex
            created_at = now.isoformat()
            marker = {
                "version": 1, "request_id": request_id,
                "status": "OFFLINE_INTENT", "created_at_utc": created_at,
                "case_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
                "old_probe_sha256": hashlib.sha256(old_probe_path.read_bytes()).hexdigest(),
                "credits": 1, "http_authorized": authorize_transport,
                "retry_authorized": False, "trading_enabled": False,
            }
            # Durable claim before any irreversible budget mutation.
            _exclusive_json(claim_path, marker)
            create_intent(journal_path, request_id=request_id,
                          authorized_at=created_at, credits=1)
            # This independently holds the stable budget lock and never refunds.
            reserve_request(path=budget_path, now=now)
            # Account for the allocation using the same ledger schema as
            # normal requests. Crash before finalize leaves journal INTENT.
            ledger["requests"][request_id] = {
                "credits": 1, "status": "PENDING",
                "authorized_at": created_at,
                "snapshot_observed_at": snapshot["observed_at"],
            }
            ledger["reserved"] += 1
            _save_json_atomic(ledger_path, ledger)
            finalize_intent(journal_path, request_id)

            return {
                "status": "OFFLINE_RESERVED",
                "request_id": request_id,
                "local_budget_reserved": True,
                "outstanding_reserved_credits": ledger["reserved"],
                "http_authorized": authorize_transport,
                "retry_authorized": False,
                "trading_enabled": False,
                "old_probe_unchanged": True,
            }
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
