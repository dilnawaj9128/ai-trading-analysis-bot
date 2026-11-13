"""Durable authorization intent journal.

Research-only. No API calls or trading execution.
All journal operations must run under the provider lock.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path


class AuthorizationJournalError(RuntimeError):
    pass


def journal_path_for(provider_path):
    provider_path = Path(provider_path)
    return provider_path.with_name(
        provider_path.name + ".authorization_journal.json"
    )


def load_journal(path):
    """Load and strictly validate the authorization journal."""
    path = Path(path)

    if not path.exists():
        return {
            "version": 1,
            "transactions": {},
        }

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise AuthorizationJournalError(
            "Authorization journal unreadable"
        ) from exc

    if (
        type(payload) is not dict
        or type(payload.get("version")) is not int
        or payload["version"] != 1
        or type(payload.get("transactions")) is not dict
    ):
        raise AuthorizationJournalError(
            "Invalid authorization journal"
        )

    for request_id, transaction in payload["transactions"].items():
        if (
            type(request_id) is not str
            or len(request_id) != 32
            or any(
                char not in "0123456789abcdef"
                for char in request_id
            )
        ):
            raise AuthorizationJournalError(
                "Invalid journal request ID"
            )

        if type(transaction) is not dict:
            raise AuthorizationJournalError(
                "Invalid journal transaction"
            )

        if transaction.get("status") not in (
            "INTENT",
            "FINALIZED",
        ):
            raise AuthorizationJournalError(
                "Invalid journal transaction status"
            )

        credits = transaction.get("credits")

        if type(credits) is not int or credits < 1:
            raise AuthorizationJournalError(
                "Invalid journal transaction credits"
            )

        authorized_at = transaction.get("authorized_at")

        if type(authorized_at) is not str:
            raise AuthorizationJournalError(
                "Invalid journal authorization timestamp"
            )

        try:
            timestamp = datetime.fromisoformat(
                authorized_at
            )
        except ValueError as exc:
            raise AuthorizationJournalError(
                "Invalid journal authorization timestamp"
            ) from exc

        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            raise AuthorizationJournalError(
                "Journal timestamp must be timezone-aware"
            )

    return payload


def save_journal(path, payload):
    path = Path(path)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".authorization_journal_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_intent(
    path, *, request_id, authorized_at, credits
):
    journal = load_journal(path)

    if request_id in journal["transactions"]:
        raise AuthorizationJournalError(
            "Duplicate authorization journal request ID"
        )

    journal["transactions"][request_id] = {
        "authorized_at": authorized_at,
        "credits": credits,
        "status": "INTENT",
    }

    save_journal(path, journal)


def finalize_intent(path, request_id):
    journal = load_journal(path)

    transaction = journal["transactions"].get(request_id)

    if transaction is None:
        raise AuthorizationJournalError(
            "Authorization journal transaction missing"
        )

    if transaction["status"] != "INTENT":
        raise AuthorizationJournalError(
            "Authorization journal transaction not pending"
        )

    transaction["status"] = "FINALIZED"
    save_journal(path, journal)
