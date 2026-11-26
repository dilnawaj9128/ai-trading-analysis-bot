"""EXPLICITLY APPROVED one-shot real EUR/USD research observation.

Reuses existing credit renewal, request guard, reservation reconciliation,
and verified live fetch. Up to 2 provider HTTP requests, never retries.
No broker execution. The hypothetical research decision is non-tradable.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def capture_live_once(*, api_key, approved=False,
                      root="data/research/prospective_accuracy"):
    if approved is not True:
        raise ValueError("Explicit up-to-two-requests approval required")
    if not api_key:
        raise ValueError("Twelve Data API key is missing")
    # IMPORTANT: only existing verified, request-bound settlement is allowed.
    from market_data.verified_reservation_settlement import reconcile_verified_historical
    from market_data.provider_credit_state import load_credit_state
    from market_data.verified_credit_renewal import renew_verified_credits_once
    from market_data.authorized_live_fetch import fetch_authorized_live_candles
    from config.market_config import create_research_config
    from research.real_prediction_campaign import (
        observe, settle_pending, preflight_observation_window,
    )
    import pandas as pd

    # Provider candles may lag wall-clock expiry by a minute or more.
    # Use a conservative two-minute buffer BEFORE spending credits. This is
    # advisory only; the fetched completed-candle timestamp is definitive.
    from research.real_prediction_campaign import _load_envelope, utc, EXPIRY
    observed = Path(root) / "observations"
    if observed.exists():
        latest_expiry = max(
            (utc(_load_envelope(p, "OBSERVATION")["expiry_time_utc"])
             for p in observed.glob("*.json")),
            default=None,
        )
        if latest_expiry is not None:
            safe_fetch_after = latest_expiry + timedelta(minutes=2)
            if datetime.now(timezone.utc) < safe_fetch_after:
                return {
                    "status": "BLOCKED_NO_HTTP",
                    "reason": "PROVIDER_CANDLE_LAG_BUFFER",
                    "next_eligible_utc": safe_fetch_after.isoformat(),
                    "provider_requests": 0,
                    "broker_orders": 0,
                }

    # Guard BEFORE ANY authorization, renewal or provider HTTP request.
    # This prevents the common accidental immediate retry after a successful
    # observation. Do not delete/overwrite old observations to evade it.
    window = preflight_observation_window(root)
    if not window["eligible"]:
        return {
            "status": "BLOCKED_NO_HTTP",
            "reason": window["reason"],
            "next_eligible_utc": window["next_eligible_utc"],
            "provider_requests": 0,
            "broker_orders": 0,
        }

    reconcile_verified_historical()
    renewed = False
    if load_credit_state() is None:
        renew_verified_credits_once(approved=True, api_key=api_key)
        renewed = True
        reconcile_verified_historical()
    config = create_research_config("quotex", "forex", "EUR/USD", "1min", 15)
    # Uses the existing unified request/credit guard and settlement receipt.
    result = fetch_authorized_live_candles(config, api_key=api_key,
                                           settle_verified=True)
    frame = result.get("frame")
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Authorized provider result contains no candle frame")
    expected = ["timestamp", "Open", "High", "Low", "Close"]
    if not set(expected).issubset(frame.columns):
        raise ValueError("Verified fetch missing required OHLC columns")
    if result.get("stale") is not False or result.get("gaps") != 0:
        raise ValueError("Fetched candle frame was stale or had gaps")
    base = Path(root) / "captures"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = frame[expected].to_csv(index=False).encode("utf-8")
    sourcehash = hashlib.sha256(content).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = base / (stamp + "_" + sourcehash[:16] + ".csv")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=base, prefix=".candles_", delete=False) as h:
            tmp = Path(h.name)
            os.fchmod(h.fileno(), 0o600)
            h.write(content)
            h.flush()
            os.fsync(h.fileno())
        os.link(tmp, dest)  # never replace previously captured evidence
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    # Reconcile earlier observations from the same new authenticated fetch
    # before trying to record a new non-overlapping observation. No extra HTTP.
    pending = settle_pending(journal=root, later_csv=dest)
    # When a model abstains, record NO TRADE as evidence rather than invent a call.
    # Wall-clock eligibility is not proof the provider has delivered a new
    # completed candle. Check the actual decision timestamp before observe().
    # A verified capture is valuable even if too early for a new observation.
    from research.real_prediction_campaign import _load_envelope, utc, EXPIRY
    observed_decision = utc(frame["timestamp"].iloc[-1]) + timedelta(minutes=1)
    obs_dir = Path(root) / "observations"
    latest_decision = max(
        (utc(_load_envelope(p, "OBSERVATION")["decision_time_utc"])
         for p in obs_dir.glob("*.json")),
        default=None,
    )
    if latest_decision is not None and observed_decision < latest_decision + EXPIRY:
        return {
            "status": "CAPTURE_SAVED_OBSERVATION_DEFERRED",
            "reason": "PROVIDER_LAST_COMPLETED_CANDLE_BEFORE_NONOVERLAP_BOUNDARY",
            "saved_csv": str(dest),
            "source_sha256": sourcehash,
            "observed_decision_utc": observed_decision.isoformat(),
            "next_required_decision_utc": (latest_decision + EXPIRY).isoformat(),
            "prior_observations_settled": len(pending["settled"]),
            "prior_observations_pending": len(pending["still_pending_or_blocked"]),
            "renewal_used": renewed,
            "maximum_provider_requests": 2,
            "broker_orders": 0,
            "live_signal": "NO TRADE",
        }
    obs_path, obs = observe(dest, journal=root)
    return {
        "saved_csv": str(dest), "source_sha256": sourcehash,
        "observation": str(obs_path),
        "research_hypothesis": obs["research_hypothesis"],
        "expiry_utc": obs["expiry_time_utc"],
        "renewal_used": renewed,
        "prior_observations_settled": len(pending["settled"]),
        "prior_observations_pending": len(pending["still_pending_or_blocked"]),
        "maximum_provider_requests": 2,
        "broker_orders": 0, "live_signal": "NO TRADE",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-up-to-two-requests", action="store_true")
    parser.add_argument("--journal", default="data/research/prospective_accuracy")
    args = parser.parse_args(argv)
    if not args.approve_up_to_two_requests:
        print("PREVIEW ONLY; 0 HTTP requests")
        print("With approval: up to 2 separately-accounted Twelve Data requests")
        return 0
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        print("BLOCKED: API key unavailable locally")
        return 2
    try:
        result = capture_live_once(api_key=key, approved=True, root=args.journal)
    except Exception as exc:
        # Do not print network exception details that could contain API keys.
        print("BLOCKED_OR_FAILED:", type(exc).__name__)
        print("NO AUTOMATIC RETRY — examine request accounting before a new approval")
        return 2
    for k, v in result.items():
        print(k.upper() + ":", v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
