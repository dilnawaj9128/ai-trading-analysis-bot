"""Stage 34: deterministic, offline, research-only forward outcome evaluation.

An earlier immutable observation and a LATER completed candle snapshot are
required. No API access, auto orders, strategy tuning, or broker parity claims.
An unverified provider feed never counts as a real-world validated outcome.
"""
from __future__ import annotations

import math
from datetime import timedelta
import pandas as pd

REQUIRED = {"timestamp", "Open", "High", "Low", "Close"}


def _time(value):
    t = pd.Timestamp(value)
    if t.tzinfo is None:
        raise ValueError("UTC-aware timestamps required")
    return t.tz_convert("UTC")


def settle_observation(observation: dict, future_candles: pd.DataFrame, *,
                       received_at, evidence_verified=False, payout=0.80,
                       simulated=False) -> dict:
    """Return one outcome without mutating the original observation.

    Status is PENDING whenever trustworthy post-expiry evidence is missing.
    Simulated settlements are explicitly marked SIMULATED, not real results.
    """
    def pending(reason):
        return {"status": "PENDING", "result": None, "pnl_units": None,
                "reason": reason, "mode": "SIMULATED" if simulated else "RESEARCH",
                "execution_enabled": False}
    if type(payout) not in (int, float) or not math.isfinite(payout) or not 0 < payout <= 1:
        raise ValueError("payout must be 0..1")
    if not isinstance(observation, dict):
        return pending("Invalid observation")
    if observation.get("status") != "VALID" or observation.get("signal") not in ("UP", "DOWN"):
        return pending("No previously validated directional observation")
    if observation.get("expiry_minutes") != 15 or observation.get("timeframe") != "1min":
        return pending("Unsupported expiry/timeframe")
    if observation.get("analysis_only") is not True or observation.get("execution_enabled") is not False:
        return pending("Observation safety provenance missing")
    if not simulated and evidence_verified is not True:
        return pending("Future provider evidence not verified")
    if simulated and evidence_verified:
        return pending("Simulated and verified-real modes cannot be mixed")
    try:
        recorded = _time(observation["observed_at_utc"])
        signal_time = _time(observation["signal_time_utc"])
        received = _time(received_at)
        entry = float(observation["entry_reference_close"])
        if not math.isfinite(entry) or entry <= 0:
            return pending("Invalid entry reference")
        if signal_time > recorded:
            return pending("Signal was not observed at time of recording")
        if received <= recorded:
            return pending("Future evidence must arrive after observation")
        expiry_time = signal_time + timedelta(minutes=15)
        if received < expiry_time:
            return pending("Expiry not reached")
        if not isinstance(future_candles, pd.DataFrame) or not REQUIRED.issubset(future_candles.columns):
            return pending("Future OHLC evidence missing")
        data = future_candles.copy()
        ts = data["timestamp"].astype(str)
        if not ts.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
            return pending("Future timestamps lack timezone offsets")
        data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="raise")
        if data.timestamp.isna().any() or data.timestamp.duplicated().any():
            return pending("Duplicate or invalid future timestamps")
        if not data.timestamp.is_monotonic_increasing:
            return pending("Future candles not chronological")
        for field in ("Open", "High", "Low", "Close"):
            data[field] = pd.to_numeric(data[field], errors="raise")
            if not data[field].map(lambda x: math.isfinite(x) and x > 0).all():
                return pending("Nonfinite or nonpositive future prices")
        if not (data.High >= data[["Open", "Close", "Low"]].max(axis=1)).all():
            return pending("Invalid future high")
        if not (data.Low <= data[["Open", "Close", "High"]].min(axis=1)).all():
            return pending("Invalid future low")
        # The timestamp denotes candle OPEN, so a 15-minute expiry uses the
        # close of the one-minute bar that ends exactly at expiry_time.
        needed_open = expiry_time - timedelta(minutes=1)
        match = data.loc[data.timestamp == needed_open]
        if len(match) != 1:
            return pending("Exact expiry candle missing")
        if received < expiry_time:
            return pending("Expiry candle unfinished")
        exit_price = float(match.iloc[0]["Close"])
        result = ("PUSH" if exit_price == entry else
                  "WIN" if (exit_price > entry) == (observation["signal"] == "UP") else "LOSS")
        pnl = payout if result == "WIN" else -1.0 if result == "LOSS" else 0.0
        return {"status": "SETTLED", "result": result, "pnl_units": pnl,
                "entry_reference_close": entry, "expiry_reference_close": exit_price,
                "expiry_time_utc": expiry_time.isoformat(),
                "settled_at_utc": received.isoformat(),
                "reason": "Hypothetical candle-close settlement; not broker execution",
                "mode": "SIMULATED" if simulated else "RESEARCH",
                "execution_enabled": False}
    except (ValueError, TypeError, KeyError, OverflowError):
        return pending("Invalid or unavailable settlement evidence")


def summarize_outcomes(outcomes: list[dict], *, payout=0.8) -> dict:
    if not 0 < payout <= 1:
        raise ValueError("Invalid payout")
    settled = [o for o in outcomes if o.get("status") == "SETTLED"]
    wins = sum(o["result"] == "WIN" for o in settled)
    losses = sum(o["result"] == "LOSS" for o in settled)
    pushes = sum(o["result"] == "PUSH" for o in settled)
    resolved = wins + losses
    return {"settled": len(settled), "pending": len(outcomes) - len(settled),
            "wins": wins, "losses": losses, "pushes": pushes,
            "win_rate": wins / resolved if resolved else None,
            "net_units": round(sum(o["pnl_units"] for o in settled), 8),
            "break_even_win_rate": 1 / (1 + payout)}
