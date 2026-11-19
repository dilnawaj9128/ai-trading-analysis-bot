"""Stage 52D Part 4C: preserve historical provider-credit evidence.

Offline only. No network access, no authorization, no state reset.
"""

import hashlib
import json
import os
from pathlib import Path


class CreditArchiveError(RuntimeError):
    pass


def archive_historical_credits(
    *,
    case_path,
    provider_path,
    archive_path,
):
    case_path = Path(case_path)
    provider_path = Path(provider_path)
    archive_path = Path(archive_path)

    if provider_path.resolve() == archive_path.resolve():
        raise CreditArchiveError("Archive must use a separate path")

    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        raw = provider_path.read_bytes()
        provider = json.loads(raw)
    except (OSError, ValueError, TypeError) as exc:
        raise CreditArchiveError(
            "Recovery evidence unavailable or invalid"
        ) from exc

    if (
        type(case) is not dict
        or case.get("schema_version") != 1
        or case.get("classification") != "UNRESOLVED_ACCOUNTING"
        or type(provider) is not dict
        or provider.get("version") != 1
    ):
        raise CreditArchiveError("Invalid recovery evidence")

    expected = case.get("source_sha256", {}).get("provider")
    actual = hashlib.sha256(raw).hexdigest()

    if (
        type(expected) is not str
        or len(expected) != 64
        or actual != expected
    ):
        raise CreditArchiveError(
            "Historical provider fingerprint mismatch"
        )

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd = os.open(
            archive_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise CreditArchiveError(
            "Historical snapshot already archived"
        ) from exc

    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())

    directory = os.open(archive_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

    return {
        "status": "HISTORICAL_CREDITS_ARCHIVED",
        "sha256": actual,
        "historical_snapshot_preserved": True,
        "new_api_request_authorized": False,
        "http_requests": 0,
    }
