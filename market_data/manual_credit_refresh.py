"""Explicit, single-use provider credit refresh.

Does not run automatically. No broker or trading execution.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from market_data.provider_credit_state import (
    DEFAULT_PATH,
    load_credit_state,
)
from market_data.twelve_data_client import (
    STATE_PATH,
    reserve_request,
)
from market_data.credit_response_handler import (
    refresh_credits_from_response,
)


class ManualRefreshBlocked(RuntimeError):
    pass


def manual_credit_refresh(
    *,
    request_callback,
    approval_id,
    explicitly_approved=False,
    provider_path=DEFAULT_PATH,
    budget_path=STATE_PATH,
    now=None,
):
    if explicitly_approved is not True:
        raise ManualRefreshBlocked("Explicit approval required")

    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ManualRefreshBlocked("Valid approval ID required")

    if not callable(request_callback):
        raise ManualRefreshBlocked("Request callback required")

    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ManualRefreshBlocked("Timezone-aware time required")

    now = now.astimezone(timezone.utc)
    provider = Path(provider_path)
    budget = Path(budget_path)

    # Reject production state paths, including alternative
    # filenames and symlink aliases inside the API usage directory.
    # This callback-based coordinator is not production-authorized.
    production_dir = Path(STATE_PATH).resolve().parent

    def is_production_state(candidate):
        resolved = candidate.resolve()
        return (
            resolved == production_dir
            or production_dir in resolved.parents
        )

    if (
        is_production_state(provider)
        or is_production_state(budget)
    ):
        raise ManualRefreshBlocked(
            "Production refresh authorization not implemented"
        )

    if provider.resolve() == budget.resolve():
        raise ManualRefreshBlocked(
            "Provider and budget paths must differ"
        )

    claim = provider.with_name(
        provider.name + ".manual_refresh_claim.json"
    )

    # This one-time workflow is limited to the observed
    # possible-first-run authorization state.
    evidence_paths = [
        provider.with_name(
            provider.name + ".authorization_journal.json"
        ),
        provider.with_name(
            provider.name + ".reservations.json"
        ),
        provider.with_name(
            provider.name + ".authorization_history.json"
        ),
        provider.with_name(
            provider.name + ".recovery_required.json"
        ),
    ]

    if any(path.exists() for path in evidence_paths):
        raise ManualRefreshBlocked(
            "Existing authorization or recovery evidence; "
            "manual review required"
        )

    if load_credit_state(path=provider, now=now) is not None:
        raise ManualRefreshBlocked(
            "Provider snapshot already fresh"
        )

    provider.parent.mkdir(parents=True, exist_ok=True)

    # Exclusive, persistent single-use claim.
    # Never delete automatically, even after failure.
    try:
        fd = os.open(
            claim,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise ManualRefreshBlocked(
            "Manual refresh already attempted; no retry"
        ) from exc

    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(
            {
                "version": 1,
                "approval_id": approval_id,
                "claimed_at": now.isoformat(),
                "status": "CLAIMED",
            },
            file,
        )
        file.flush()
        os.fsync(file.fileno())

    directory_fd = os.open(provider.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

    # Claim persists if budget reservation or transport fails.
    reserve_request(path=budget, now=now)

    try:
        response = request_callback()

        status = getattr(response, "status_code", None)
        if type(status) is not int or not 200 <= status < 300:
            raise ValueError("Unsuccessful provider HTTP status")

        payload = response.json()
        if (
            not isinstance(payload, dict)
            or payload.get("status") == "error"
            or not isinstance(payload.get("values"), list)
            or not payload["values"]
        ):
            raise ValueError("Invalid provider data response")

        refresh = refresh_credits_from_response(
            response,
            path=provider,
            now=datetime.now(timezone.utc),
        )

        if refresh.updated is not True:
            raise ValueError("Provider credits not updated")

    except Exception:
        # No refund, reset or automatic retry.
        return {
            "status": "UNCERTAIN",
            "credits_left": None,
            "retry_allowed": False,
            "trading_enabled": False,
        }

    return {
        "status": "SNAPSHOT_REFRESHED",
        "credits_left": refresh.credits_left,
        "retry_allowed": False,
        "settlement_authorized": False,
        "trading_enabled": False,
    }


def prepare_and_record_refresh_offline(
    *,
    approval_path,
    lifecycle_path,
    approval_id,
    execution_path,
    budget_path,
    now,
):
    """Prepare one durable offline execution.

    Never reserve API credits, record an HTTP attempt,
    execute HTTP, or authorize settlement.
    """
    from market_data.manual_refresh_execution_state import (
        create_execution,
    )

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ManualRefreshBlocked("Timezone-aware time required")

    paths = [
        Path(approval_path),
        Path(lifecycle_path),
        Path(execution_path),
        Path(budget_path),
    ]

    production_dir = Path(STATE_PATH).resolve().parent

    for path in paths:
        resolved = path.resolve()
        if resolved == production_dir or production_dir in resolved.parents:
            raise ManualRefreshBlocked(
                "Production execution authorization not implemented"
            )

    approval, lifecycle, execution, budget = paths

    protected = paths + [
        approval.with_name(approval.name + ".consumed"),
        lifecycle.with_name(lifecycle.name + ".lock"),
        execution.with_name(execution.name + ".lock"),
        budget.with_name(budget.name + ".lock"),
    ]

    if len({p.resolve() for p in protected}) != len(protected):
        raise ManualRefreshBlocked("Overlapping state paths")

    prepared = create_execution(
        approval_path=approval,
        lifecycle_path=lifecycle,
        approval_id=approval_id,
        execution_path=execution,
    )

    return {
        "approval_claim_id": prepared["approval_claim_id"],
        "attempt_id": prepared["attempt_id"],
        "status": "PREPARED",
        "budget_reserved": False,
        "http_executed": False,
        "retry_allowed": False,
        "settlement_authorized": False,
        "trading_enabled": False,
    }


def refresh_production_provider_credits(
    *,
    approval_id,
    explicitly_approved=False,
    api_key=None,
    provider_path=DEFAULT_PATH,
    budget_path=STATE_PATH,
    approval_path="data/api_usage/credit_refresh_claim.json",
    lifecycle_path="data/api_usage/credit_refresh_lifecycle.json",
    execution_path="data/api_usage/credit_refresh_execution.json",
):
    """One explicitly approved, single-use Twelve Data credit refresh.

    A request may consume API credits. No automatic retry or trading.
    Does not settle provider reservations.
    """
    import requests

    from market_data import twelve_data_client as td
    from market_data.manual_refresh_preparation import (
        prepare_manual_refresh,
    )
    from market_data.manual_refresh_execution_state import (
        create_execution,
        reserve_execution_budget,
        record_request_attempt,
        mark_uncertain,
    )

    if explicitly_approved is not True:
        raise ManualRefreshBlocked("Explicit approval required")

    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ManualRefreshBlocked("Valid approval ID required")

    key = api_key if api_key is not None else os.environ.get(
        "TWELVE_DATA_API_KEY"
    )
    if not key:
        raise ManualRefreshBlocked("Twelve Data API key missing")

    provider = Path(provider_path)
    budget = Path(budget_path)
    approval = Path(approval_path)
    lifecycle = Path(lifecycle_path)
    execution = Path(execution_path)

    marker = approval.with_name(approval.name + ".consumed")

    protected = [
        provider, budget, approval, lifecycle, execution, marker,
        provider.with_name(provider.name + ".lock"),
        budget.with_name(budget.name + ".lock"),
        lifecycle.with_name(lifecycle.name + ".lock"),
        execution.with_name(execution.name + ".lock"),
    ]

    if len({p.resolve() for p in protected}) != len(protected):
        raise ManualRefreshBlocked("Overlapping state paths")

    # Recovery or inconsistent authorization evidence needs review.
    recovery = provider.with_name(
        provider.name + ".recovery_required.json"
    )
    if recovery.exists():
        raise ManualRefreshBlocked(
            "Recovery evidence exists; manual review required"
        )

    now = datetime.now(timezone.utc)

    # Preserve existing fresh snapshot and avoid needless request.
    if load_credit_state(path=provider, now=now) is not None:
        raise ManualRefreshBlocked(
            "Fresh provider snapshot already available"
        )

    # Approval claim and consumption marker are persistent.
    prepared = prepare_manual_refresh(
        approval_id=approval_id,
        approval_path=approval,
        lifecycle_path=lifecycle,
        explicitly_approved=True,
        now=now,
    )

    created = create_execution(
        approval_path=approval,
        lifecycle_path=lifecycle,
        approval_id=approval_id,
        execution_path=execution,
    )

    if created["attempt_id"] != prepared["attempt_id"]:
        raise ManualRefreshBlocked("Attempt identity mismatch")

    # A durable reservation-start marker is written first.
    reserve_execution_budget(
        execution_path=execution,
        budget_path=budget,
        now=now,
    )

    # Persist intent before sending the HTTP request.
    record_request_attempt(execution_path=execution)

    try:
        response = requests.get(
            td.API_URL,
            params={
                "symbol": "EUR/USD",
                "interval": "1min",
                "outputsize": 10,
                "timezone": "UTC",
                "apikey": key,
                "format": "JSON",
            },
            timeout=td.TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        payload = response.json()
        if (
            not isinstance(payload, dict)
            or payload.get("status") == "error"
            or not isinstance(payload.get("values"), list)
            or not payload["values"]
        ):
            raise ValueError("Invalid provider candle response")

        refresh = refresh_credits_from_response(
            response,
            path=provider,
            now=datetime.now(timezone.utc),
        )

        if refresh.updated is not True:
            raise ValueError(
                "Provider credit headers missing or invalid"
            )

    except Exception:
        # Preserve authorization and quota evidence.
        # Never retry automatically.
        try:
            mark_uncertain(execution_path=execution)
        except Exception:
            pass

        return {
            "status": "UNCERTAIN",
            "snapshot_updated": False,
            "retry_allowed": False,
            "trading_enabled": False,
        }

    # Snapshot refresh is not request-specific settlement.
    # Keep execution unresolved until reconciliation is implemented.
    try:
        mark_uncertain(execution_path=execution)
    except Exception as exc:
        raise ManualRefreshBlocked(
            "Snapshot refreshed but execution evidence "
            "requires manual review"
        ) from exc

    return {
        "status": "SNAPSHOT_REFRESHED_UNRECONCILED",
        "snapshot_updated": True,
        "credits_left": refresh.credits_left,
        "retry_allowed": False,
        "settlement_authorized": False,
        "trading_enabled": False,
    }
