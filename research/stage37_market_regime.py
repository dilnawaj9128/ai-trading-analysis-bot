"""Stage 37: exploratory market-regime research.

Read-only offline analysis of Stage 36 walk-forward trades.
No provider calls, trading orders or strategy optimization.
"""

import math
from collections import defaultdict

from indicators import calculate_indicators
from scripts.run_stage36_walk_forward import walk_forward

# Fixed descriptive thresholds, NOT optimized on test outcomes.
STRONG_TREND_ATR_RATIO = 0.35
HIGH_VOLATILITY_ATR_PCT = 0.05
MIN_GROUP_SAMPLES = 30


def classify_regime(row):
    """Use indicators known at the signal candle only."""

    try:
        close = float(row["Close"])
        atr = float(row["ATR_14"])
        ema20 = float(row["EMA_20"])
        ema50 = float(row["EMA_50"])
        rsi = float(row["RSI_14"])
    except (KeyError, ValueError, TypeError):
        return {
            "trend": "UNKNOWN",
            "volatility": "UNKNOWN",
            "rsi_zone": "UNKNOWN",
        }

    values = (close, atr, ema20, ema50, rsi)

    if not all(math.isfinite(x) for x in values):
        return {
            "trend": "UNKNOWN",
            "volatility": "UNKNOWN",
            "rsi_zone": "UNKNOWN",
        }

    if close <= 0 or atr <= 0:
        return {
            "trend": "UNKNOWN",
            "volatility": "UNKNOWN",
            "rsi_zone": "UNKNOWN",
        }

    trend_strength = abs(ema20 - ema50) / atr
    atr_pct = (atr / close) * 100

    trend = (
        "STRONG"
        if trend_strength >= STRONG_TREND_ATR_RATIO
        else "WEAK"
    )

    volatility = (
        "HIGH"
        if atr_pct >= HIGH_VOLATILITY_ATR_PCT
        else "LOW"
    )

    if rsi > 55:
        rsi_zone = "BULLISH"
    elif rsi < 45:
        rsi_zone = "BEARISH"
    else:
        rsi_zone = "NEUTRAL"

    return {
        "trend": trend,
        "volatility": volatility,
        "rsi_zone": rsi_zone,
        "trend_strength": round(trend_strength, 6),
        "atr_pct": round(atr_pct, 6),
    }


def enrich_trades(candles, trades, indicator_fn=None):
    """Annotate trades using ONLY data available at signal time."""

    if indicator_fn is None:
        indicator_fn = calculate_indicators

    enriched_trades = []

    for trade in trades:
        index = trade["signal_index"]

        if type(index) is not int:
            raise ValueError("Invalid signal index")

        if not 0 <= index < len(candles):
            raise ValueError("Signal index outside candle dataset")

        if trade["expiry_index"] <= index:
            raise ValueError("Invalid expiry chronology")

        # Strict causal prefix: no future candles supplied.
        prefix = candles.iloc[:index + 1].copy()

        indicators = indicator_fn(prefix)
        if indicators is None or indicators.empty:
            raise ValueError("Indicator output empty")

        regime = classify_regime(indicators.iloc[-1])

        enriched_trades.append({
            **trade,
            **regime,
        })

    return enriched_trades


def group_performance(trades, group_keys, payout=0.8):
    """Descriptive results only; never auto-select a strategy."""

    if not 0 < payout <= 1:
        raise ValueError("Invalid payout")

    groups = defaultdict(list)

    for trade in trades:
        if trade["result"] not in ("WIN", "LOSS", "PUSH"):
            raise ValueError("Unknown outcome")

        key = tuple(trade[field] for field in group_keys)
        groups[key].append(trade)

    results = []

    for key, rows in sorted(groups.items()):
        wins = sum(t["result"] == "WIN" for t in rows)
        losses = sum(t["result"] == "LOSS" for t in rows)
        pushes = sum(t["result"] == "PUSH" for t in rows)

        resolved = wins + losses
        win_rate = wins / resolved if resolved else None
        net_units = round(wins * payout - losses, 8)

        results.append({
            "group": "/".join(str(x) for x in key),
            "trades": len(rows),
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "win_rate": win_rate,
            "net_units": net_units,
            "evidence": (
                "SMALL SAMPLE"
                if resolved < MIN_GROUP_SAMPLES
                else "EXPLORATORY ONLY"
            ),
        })

    return results


def run_regime_analysis(
    candles,
    initial_train=720,
    test_size=180,
    payout=0.8,
    min_training_trades=30,
    walk_forward_fn=None,
    indicator_fn=None,
):
    """Reuse historical out-of-sample folds; do not retune."""

    if walk_forward_fn is None:
        walk_forward_fn = walk_forward

    report = walk_forward_fn(
        candles,
        initial_train=initial_train,
        test_size=test_size,
        payout=payout,
        min_training_trades=min_training_trades,
    )

    trades = enrich_trades(
        candles,
        report["test_trades"],
        indicator_fn=indicator_fn,
    )

    by_trend = group_performance(
        trades, ("trend",), payout
    )

    by_volatility = group_performance(
        trades, ("volatility",), payout
    )

    by_combined = group_performance(
        trades, ("trend", "volatility"), payout
    )

    total = group_performance(trades, (), payout)

    # Cross-check against Stage 36 results.
    if total:
        if total[0]["resolved"] != report["aggregate"]["resolved"]:
            raise AssertionError("Resolved outcome mismatch")

        if total[0]["net_units"] != report["aggregate"]["net_units"]:
            raise AssertionError("Net P/L mismatch")

    return {
        "total_trades": len(trades),
        "trades": trades,
        "by_trend": by_trend,
        "by_volatility": by_volatility,
        "by_combined": by_combined,
        "aggregate": report["aggregate"],
        "analysis_only": True,
        "execution_enabled": False,
    }
