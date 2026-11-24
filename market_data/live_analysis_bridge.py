"""Analyze the *same* verified normal-fetch candle frame, without more HTTP.

Provider data is not evidence of Quotex broker-feed parity. Directional
research outputs remain NO TRADE. No orders, broker calls, or file writes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

import pandas as pd


def analyze_fetched_candles(result, *, now=None, indicator_engine=None,
                            market_engine=None, signal_engine=None):
    """Validate completed EUR/USD 1m candles and generate research observations.

    All three engines can be injected for deterministic offline tests. Without
    injection the project's already existing analysis engines are imported.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware analysis clock required")
    now = now.astimezone(timezone.utc)
    if not isinstance(result, dict) or result.get("analysis_only") is not True or result.get("execution_enabled") is not False:
        raise ValueError("Untrusted or executable fetch result")
    if result.get("symbol") != "EUR/USD" or result.get("interval") != "1min":
        raise ValueError("Unexpected research market")
    frame = result.get("frame")
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Validated candle frame required")
    needed = {"timestamp", "Open", "High", "Low", "Close"}
    if not needed.issubset(frame.columns) or len(frame) < 60:
        raise ValueError("At least 60 complete OHLC candles required")
    if type(result.get("candles")) is not int or result["candles"] != len(frame):
        raise ValueError("Candle count mismatch")
    clean = frame[["timestamp", "Open", "High", "Low", "Close"]].copy(deep=True)
    stamps = pd.to_datetime(clean["timestamp"], utc=True, errors="raise")
    if stamps.isna().any() or not stamps.is_monotonic_increasing or stamps.duplicated().any():
        raise ValueError("Non-monotonic, duplicate or invalid timestamps")
    clean["timestamp"] = stamps
    for column in ("Open", "High", "Low", "Close"):
        clean[column] = pd.to_numeric(clean[column], errors="raise")
        if not clean[column].map(math.isfinite).all() or (clean[column] <= 0).any():
            raise ValueError("Invalid OHLC")
    if not (clean["High"] >= clean[["Open", "Close", "Low"]].max(axis=1)).all():
        raise ValueError("Invalid high")
    if not (clean["Low"] <= clean[["Open", "Close", "High"]].min(axis=1)).all():
        raise ValueError("Invalid low")
    gaps = int((stamps.diff().dropna() != pd.Timedelta(minutes=1)).sum())
    age = (now - stamps.iloc[-1].to_pydatetime()).total_seconds()
    if age < 60:
        raise ValueError("Future or uncompleted candle")
    stale = age > 180
    if indicator_engine is None:
        from analysis.live_engine import analyze_live_candles
        indicator_engine = analyze_live_candles
    if market_engine is None:
        from analysis.smart_market import assess_market
        market_engine = assess_market
    if signal_engine is None:
        from strategy.signal_engine import generate_signal
        signal_engine = generate_signal
    indicators_result = indicator_engine(clean)
    if not isinstance(indicators_result, dict) or not isinstance(indicators_result.get("frame"), pd.DataFrame):
        raise ValueError("Invalid indicator engine result")
    enriched = indicators_result["frame"]
    if len(enriched) != len(clean) or not {"Close"}.issubset(enriched.columns):
        raise ValueError("Indicator engine altered candle count")
    market = market_engine(indicators_result, stale=stale, gaps=gaps)
    if not isinstance(market, dict):
        raise ValueError("Invalid market assessment")
    decision = signal_engine(enriched, expiry_minutes=15, data_mode="unknown",
                             data_quality_status="VALID" if not stale and gaps == 0 else "INVALID")
    if not isinstance(decision, dict) or decision.get("signal") != "NO TRADE" or decision.get("expiry_minutes") != 15:
        raise ValueError("Unverified feed must remain NO TRADE")
    last = enriched.iloc[-1]
    indicator_names = ("Close", "EMA_9", "EMA_20", "EMA_21", "EMA_50", "RSI_14", "MACD", "MACD_signal", "ATR_14")
    observations = {}
    for name in indicator_names:
        if name in last and pd.notna(last[name]) and math.isfinite(float(last[name])):
            observations[name] = round(float(last[name]), 8)
    return {
        "status": "RESEARCH_ANALYSIS_READY",
        "symbol": "EUR/USD", "timeframe": "1min", "expiry_minutes": 15,
        "candles": len(clean), "latest_utc": stamps.iloc[-1].isoformat(),
        "age_seconds": round(age, 2), "stale": stale, "gaps": gaps,
        "indicators": observations, "market_condition": market.get("condition", "unknown"),
        "market_explanation": market.get("explanation", ""),
        "signal": "NO TRADE", "reasons": decision.get("reasons", []) + ["Broker/feed parity is unverified"],
        "feed_mode": "unverified", "analysis_only": True,
        "execution_enabled": False, "broker_orders": 0, "extra_http_requests": 0,
    }
