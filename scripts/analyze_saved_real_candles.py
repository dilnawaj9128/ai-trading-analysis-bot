"""Offline analysis of saved Twelve Data completed EUR/USD candles.

No network, no orders, no API credits. Stale and unverified feed modes
are deliberately not promoted to directional signals.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analysis.live_engine import analyze_live_candles
from analysis.smart_market import assess_market
from strategy.signal_engine import generate_signal


def load_validated_csv(path: Path, *, now: datetime) -> tuple[pd.DataFrame, int, float]:
    if not path.is_file():
        raise ValueError(f"CSV not found: {path}")
    frame = pd.read_csv(path)
    required = {"timestamp", "Open", "High", "Low", "Close"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing CSV columns: {sorted(required - set(frame.columns))}")
    frame = frame[["timestamp", "Open", "High", "Low", "Close"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if frame["timestamp"].isna().any() or not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("Missing, unordered or invalid timestamps")
    if frame["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps")
    if len(frame) < 60:
        raise ValueError("At least 60 completed candles required")

    for name in ("Open", "High", "Low", "Close"):
        frame[name] = pd.to_numeric(frame[name], errors="raise")
        if not frame[name].map(math.isfinite).all() or (frame[name] <= 0).any():
            raise ValueError(f"Invalid {name} values")
    if not (frame["High"] >= frame[["Open", "Close", "Low"]].max(axis=1)).all():
        raise ValueError("Invalid high price")
    if not (frame["Low"] <= frame[["Open", "Close", "High"]].min(axis=1)).all():
        raise ValueError("Invalid low price")

    diffs = frame["timestamp"].diff().dropna()
    if (diffs <= pd.Timedelta(0)).any():
        raise ValueError("Non-increasing timestamps")
    gaps = int((diffs != pd.Timedelta(minutes=1)).sum())
    latest = frame["timestamp"].iloc[-1].to_pydatetime()
    # Validate last 1m candle has completed; never evaluate a future candle.
    age = (now - latest).total_seconds()
    if age < 60:
        raise ValueError("Latest candle is incomplete or in future")
    return frame, gaps, age


def analyze(path: Path, *, now: datetime) -> dict:
    frame, gaps, age = load_validated_csv(path, now=now)
    stale = age > 180
    analysis = analyze_live_candles(frame)
    enriched = analysis["frame"]
    market = assess_market(analysis, stale=stale, gaps=gaps)
    # This CSV alone does not prove a provider-defined live vs delayed feed.
    # Use unknown mode, so the existing signal engine safely returns NO TRADE.
    decision = generate_signal(
        enriched,
        expiry_minutes=15,
        data_mode="unknown",
        data_quality_status="VALID" if (not stale and gaps == 0) else "INVALID",
    )
    last = enriched.iloc[-1]
    keys = ["Close", "EMA_20", "EMA_50", "RSI_14", "MACD", "MACD_signal", "ATR_14"]
    indicators = {}
    for key in keys:
        if key in last and pd.notna(last[key]):
            indicators[key] = round(float(last[key]), 8)
    return {
        "source": "saved_twelve_data_csv",
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "candles": len(frame),
        "latest_utc": frame["timestamp"].iloc[-1].isoformat(),
        "age_seconds": round(age, 2),
        "gaps": gaps,
        "stale": stale,
        "feed_mode": "unverified",
        "indicators": indicators,
        "market_condition": market["condition"],
        "market_explanation": market["explanation"],
        "signal": decision["signal"],
        "expiry_minutes": decision["expiry_minutes"],
        "reasons": decision["reasons"],
        "analysis_only": True,
        "execution_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=Path("data/real_market/latest_eurusd_completed.csv"))
    args = parser.parse_args()
    result = analyze(args.csv, now=datetime.now(timezone.utc))
    print(json.dumps(result, indent=2))
    print("Research only: no API request or trading action performed.")


if __name__ == "__main__":
    main()
