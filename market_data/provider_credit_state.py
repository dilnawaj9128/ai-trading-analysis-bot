"""Persistent provider credit state. No API calls."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from market_data.api_credit_monitor import CreditSnapshot


DEFAULT_PATH = Path("data/api_usage/provider_credits.json")


def _utc(value):
    if value.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def save_credit_state(
    snapshot: CreditSnapshot,
    *,
    path=DEFAULT_PATH,
    now=None,
):
    if not isinstance(snapshot, CreditSnapshot):
        raise ValueError("CreditSnapshot required")

    if snapshot.credits_left is not None and (
        type(snapshot.credits_left) is not int
        or snapshot.credits_left < 0
    ):
        raise ValueError("Invalid credits_left")

    if snapshot.credits_used is not None and (
        type(snapshot.credits_used) is not int
        or snapshot.credits_used < 0
    ):
        raise ValueError("Invalid credits_used")

    now = _utc(now or datetime.now(timezone.utc))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "observed_at": now.isoformat(),
        "credits_used": snapshot.credits_used,
        "credits_left": snapshot.credits_left,
    }

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=".credits_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return path


def load_credit_state(
    *,
    path=DEFAULT_PATH,
    now=None,
    max_age_seconds=300,
):
    if type(max_age_seconds) is not int or max_age_seconds < 0:
        raise ValueError("Invalid max_age_seconds")

    path = Path(path)

    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text())

        if type(payload) is not dict or payload.get("version") != 1:
            raise ValueError("Invalid state version")

        observed_at = datetime.fromisoformat(
            payload["observed_at"]
        )
        observed_at = _utc(observed_at)

        now = _utc(now or datetime.now(timezone.utc))
        age = (now - observed_at).total_seconds()

        if age < 0 or age > max_age_seconds:
            return None

        used = payload["credits_used"]
        left = payload["credits_left"]

        for value in (used, left):
            if value is not None and (
                type(value) is not int or value < 0
            ):
                raise ValueError("Invalid credit value")

        return CreditSnapshot(
            credits_used=used,
            credits_left=left,
            low_credits=left is not None and left < 20,
            information_available=used is not None or left is not None,
        )

    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValueError("Invalid provider credit state") from exc
