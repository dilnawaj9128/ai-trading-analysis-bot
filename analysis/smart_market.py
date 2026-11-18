"""Research-only market condition classification from completed candles."""
from __future__ import annotations

import math


def _number(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def assess_market(analysis: dict, *, stale: bool = False, gaps: int = 0) -> dict:
    """Describe indicator agreement; never generate a trade signal."""
    base = {
        "condition": "DATA UNAVAILABLE",
        "explanation": "Market assessment unavailable.",
        "ema_view": "Unavailable",
        "rsi_view": "Unavailable",
        "macd_view": "Unavailable",
        "agreement": 0,
        "analysis_only": True,
        "execution_enabled": False,
        "directional_backtesting_allowed": False,
    }
    if stale or gaps:
        base["explanation"] = "Stale candles or timestamp gaps detected; assessment blocked."
        return base
    latest = analysis.get("latest", {})
    if not isinstance(latest, dict):
        return base
    ema9 = _number(latest.get("EMA_9"))
    ema21 = _number(latest.get("EMA_21"))
    rsi = _number(latest.get("RSI_14"))
    if any(x is None for x in (ema9, ema21, rsi)) or not 0 <= rsi <= 100:
        base["explanation"] = "Required indicators are missing or invalid."
        return base

    # MACD column names depend on the existing indicator implementation.
    macd_keys = [k for k in latest if k.upper() == "MACD"]
    signal_keys = [k for k in latest if "SIGNAL" in k.upper() and "MACD" in k.upper()]
    if not signal_keys:
        signal_keys = [k for k in latest if k.upper() == "SIGNAL"]
    macd = _number(latest[macd_keys[0]]) if macd_keys else None
    signal = _number(latest[signal_keys[0]]) if signal_keys else None

    ema_vote = 1 if ema9 > ema21 else (-1 if ema9 < ema21 else 0)
    # RSI > 50 / < 50 reflects relative momentum, not a trade recommendation.
    rsi_vote = 1 if rsi > 50 else (-1 if rsi < 50 else 0)
    macd_vote = (1 if macd > signal else (-1 if macd < signal else 0)) if macd is not None and signal is not None else None

    base["ema_view"] = "EMA 9 above EMA 21" if ema_vote > 0 else "EMA 9 below EMA 21" if ema_vote < 0 else "EMAs equal"
    base["rsi_view"] = f"RSI {rsi:.1f} ({'above' if rsi > 50 else 'below' if rsi < 50 else 'at'} midpoint 50)"
    base["macd_view"] = ("MACD above signal" if macd_vote > 0 else "MACD below signal" if macd_vote < 0 else "MACD equals signal") if macd_vote is not None else "MACD comparison unavailable"

    votes = [ema_vote, rsi_vote] + ([macd_vote] if macd_vote is not None else [])
    positive = sum(v == 1 for v in votes)
    negative = sum(v == -1 for v in votes)
    base["agreement"] = max(positive, negative)
    if positive == len(votes) and len(votes) == 3:
        base["condition"] = "BULLISH ALIGNMENT"
        base["explanation"] = "EMA, RSI and MACD observations align upward; this does not predict the next candle."
    elif negative == len(votes) and len(votes) == 3:
        base["condition"] = "BEARISH ALIGNMENT"
        base["explanation"] = "EMA, RSI and MACD observations align downward; this does not predict the next candle."
    else:
        base["condition"] = "MIXED / INCONCLUSIVE"
        base["explanation"] = "Indicators are mixed or insufficient for a three-indicator agreement assessment."
    return base
