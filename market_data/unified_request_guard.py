"""Conservative atomic provider-credit authorization.

Provider-reported credits are never modified here.
All local reservations are stored in one locked ledger.
Research-only: no HTTP calls or trading execution.
"""

import fcntl
import json
import os
import tempfile
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from market_data.authorization_journal import (
    journal_path_for,
    load_journal,
    create_intent,
    finalize_intent,
    AuthorizationJournalError,
)
from market_data.pre_request_credit_gate import check_before_request
from market_data.provider_credit_guard import ProviderCreditLimitReached
from market_data.provider_credit_state import DEFAULT_PATH
from market_data.twelve_data_client import STATE_PATH, reserve_request
from market_data.minute_reservation_headroom import minute_pending_credits


@dataclass(frozen=True)
class RequestAuthorization:
    authorized: bool
    provider_credits_remaining: int
    local_budget_reserved: bool
    request_id: str = ""


def _save_json_atomic(path, payload):
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=".reservations_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
        _sync_directory(path.parent)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _save_authorization_history(path):
    """Persist independent initialization evidence atomically."""
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".authorization_history_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(
                {"version": 1, "initialized": True},
                handle,
            )
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
        _sync_directory(path.parent)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _load_ledger(path):
    if not path.exists():
        return {
            "version": 2,
            "reserved": 0,
            "legacy_reserved": 0,
            "requests": {},
        }

    try:
        payload = json.loads(path.read_text())

        if type(payload) is not dict:
            raise ValueError("Invalid ledger")

        version = payload.get("version")

        if version == 1:
            # Legacy V1 has aggregate reservations only.
            # Reject unknown fields instead of silently
            # discarding potentially important evidence.
            if set(payload) != {"version", "reserved"}:
                raise ValueError(
                    "Invalid legacy ledger structure"
                )

            reserved = payload.get("reserved")

            if type(reserved) is not int or reserved < 0:
                raise ValueError("Invalid legacy reservation")

            return {
                "version": 2,
                "reserved": reserved,
                "legacy_reserved": reserved,
                "requests": {},
            }

        if version != 2:
            raise ValueError("Unsupported ledger version")

        reserved = payload.get("reserved")
        legacy = payload.get("legacy_reserved")
        requests = payload.get("requests")

        if (
            type(reserved) is not int
            or reserved < 0
            or type(legacy) is not int
            or legacy < 0
            or type(requests) is not dict
        ):
            raise ValueError("Invalid ledger structure")

        outstanding = legacy

        for request_id, entry in requests.items():
            if (
                not isinstance(request_id, str)
                or not request_id
                or type(entry) is not dict
                or type(entry.get("credits")) is not int
                or entry["credits"] < 1
                or entry.get("status") not in (
                    "PENDING",
                    "SETTLED",
                    "UNCERTAIN",
                )
            ):
                raise ValueError("Invalid reservation entry")

            if entry["status"] != "SETTLED":
                outstanding += entry["credits"]

        if outstanding != reserved:
            raise ValueError("Reservation accounting mismatch")

        return payload

    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("Invalid reservation ledger") from exc



def _sync_directory(directory):
    """Persist directory-entry changes where supported."""
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _create_recovery_marker(
    path, *, request_id, authorized_at, credits
):
    """Create durable transaction intent before budget reservation."""
    payload = {
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": request_id,
        "authorized_at": authorized_at,
        "credits": credits,
    }

    # Exclusive creation prevents silently replacing a marker.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())

    _sync_directory(path.parent)


def _clear_recovery_marker(path):
    path.unlink()
    _sync_directory(path.parent)


def authorize_request(
    *,
    provider_state_path=DEFAULT_PATH,
    local_budget_path=STATE_PATH,
    now=None,
    required_credits=1,
    reserve_credits=20,
    max_age_seconds=300,
):
    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")

    provider_path = Path(provider_state_path)

    lock_path = provider_path.with_name(
        provider_path.name + ".lock"
    )
    ledger_path = provider_path.with_name(
        provider_path.name + ".reservations.json"
    )

    provider_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path = journal_path_for(provider_path)

    history_path = provider_path.with_name(
        provider_path.name + ".authorization_history.json"
    )

    recovery_path = provider_path.with_name(
        provider_path.name + ".recovery_required.json"
    )

    with open(lock_path, "a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        # Verify that the acquired lock still belongs to the
        # lock file currently reachable at the expected path.
        try:
            locked_stat = os.fstat(lock_file.fileno())
            path_stat = os.stat(lock_path)
        except OSError as exc:
            raise RuntimeError(
                "Authorization lock identity unavailable"
            ) from exc

        if (
            locked_stat.st_dev != path_stat.st_dev
            or locked_stat.st_ino != path_stat.st_ino
        ):
            raise RuntimeError(
                "Authorization lock identity changed"
            )

        try:
            if recovery_path.exists():
                from market_data.provider_credit_guard import (
                    ProviderCreditStatusUnknown,
                )
                raise ProviderCreditStatusUnknown(
                    "Authorization blocked: recovery required"
                )

            # Existing reservation evidence must not be silently
            # accepted with a missing authorization journal.
            if not journal_path.exists() and ledger_path.exists():
                existing_ledger = _load_ledger(ledger_path)

                # Legacy v1 ledgers predate the authorization
                # journal. Preserve their existing reservations.
                raw_ledger = json.loads(
                    ledger_path.read_text(encoding="utf-8")
                )

                is_legacy = (
                    type(raw_ledger) is dict
                    and type(raw_ledger.get("version")) is int
                    and raw_ledger["version"] == 1
                )

                if not is_legacy and (
                    existing_ledger["requests"]
                    or existing_ledger["reserved"] > 0
                ):
                    raise AuthorizationJournalError(
                        "Authorization blocked: journal missing "
                        "for existing reservations"
                    )

            # A previously initialized authorization history
            # must never silently become a fresh installation.
            if history_path.exists():
                try:
                    history = json.loads(
                        history_path.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError) as exc:
                    raise AuthorizationJournalError(
                        "Authorization history unreadable"
                    ) from exc

                if (
                    type(history) is not dict
                    or history.get("version") != 1
                    or history.get("initialized") is not True
                ):
                    raise AuthorizationJournalError(
                        "Invalid authorization history"
                    )

                if not journal_path.exists() or not ledger_path.exists():
                    raise AuthorizationJournalError(
                        "Authorization blocked: missing journal "
                        "or ledger evidence"
                    )

            journal = load_journal(journal_path)
            if any(
                entry.get("status") != "FINALIZED"
                for entry in journal["transactions"].values()
            ):
                raise AuthorizationJournalError(
                    "Authorization blocked: unresolved journal intent"
                )

            decision = check_before_request(
                path=provider_path,
                now=now,
                required_credits=required_credits,
                reserve_credits=reserve_credits,
                max_age_seconds=max_age_seconds,
            )

            ledger = _load_ledger(ledger_path)

            # Cross-check independently persisted authorization
            # evidence before reserving any additional budget.
            journal_transactions = journal["transactions"]
            ledger_requests = ledger["requests"]

            for recorded_id, transaction in journal_transactions.items():
                reservation = ledger_requests.get(recorded_id)

                if reservation is None:
                    raise AuthorizationJournalError(
                        "Authorization blocked: journal-ledger "
                        "request mismatch"
                    )

                if reservation["credits"] != transaction["credits"]:
                    raise AuthorizationJournalError(
                        "Authorization blocked: journal-ledger "
                        "credit mismatch"
                    )

            for recorded_id in ledger_requests:
                if recorded_id not in journal_transactions:
                    raise AuthorizationJournalError(
                        "Authorization blocked: ledger request "
                        "missing from journal"
                    )

            # Provider credit headers describe this minute. Older outstanding
            # requests stay in the durable ledger, but are not charged against
            # the new minute's independently enforced quota.
            observed = datetime.fromisoformat(
                json.loads(provider_path.read_text(encoding="utf-8"))["observed_at"]
            )
            available = (
                decision.remaining_credits
                - minute_pending_credits(ledger, now=now, observed_at=observed)
            )

            if available < required_credits + reserve_credits:
                raise ProviderCreditLimitReached(
                    "Insufficient credits after local reservations"
                )

            # Generate the request ID before any budget mutation.
            request_id = uuid.uuid4().hex

            if request_id in ledger["requests"]:
                raise ValueError("Duplicate request ID")

            # Persist initialization evidence before creating
            # the first authorization intent.
            if not history_path.exists():
                _save_authorization_history(history_path)

            create_intent(
                journal_path,
                request_id=request_id,
                authorized_at=now.astimezone(timezone.utc).isoformat(),
                credits=required_credits,
            )

            # Durable write-ahead intent: never refund automatically.
            _create_recovery_marker(
                recovery_path,
                request_id=request_id,
                authorized_at=now.astimezone(timezone.utc).isoformat(),
                credits=required_credits,
            )

            # Local request quota must succeed before ledger commit.
            reserve_request(
                path=local_budget_path,
                now=now,
            )

            # Read the snapshot timestamp while holding the
            # same lock used by provider-credit refresh.
            provider_payload = json.loads(
                provider_path.read_text()
            )

            snapshot_observed_at = provider_payload["observed_at"]

            # Preserve strict timezone-aware metadata.
            observed = datetime.fromisoformat(
                snapshot_observed_at
            )

            if observed.tzinfo is None:
                raise ValueError(
                    "Provider observation timestamp must be timezone-aware"
                )

            ledger["requests"][request_id] = {
                "credits": required_credits,
                "status": "PENDING",
                "authorized_at": now.astimezone(
                    timezone.utc
                ).isoformat(),
                "snapshot_observed_at": observed.astimezone(
                    timezone.utc
                ).isoformat(),
            }

            ledger["reserved"] += required_credits

            _save_json_atomic(ledger_path, ledger)

            finalize_intent(journal_path, request_id)

            # A failed cleanup leaves authorization blocked,
            # rather than risking an untracked new request.
            _clear_recovery_marker(recovery_path)

            return RequestAuthorization(
                authorized=True,
                provider_credits_remaining=(
                    available - required_credits
                ),
                local_budget_reserved=True,
                request_id=request_id,
            )

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
