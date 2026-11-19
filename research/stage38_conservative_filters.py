"""Stage 38: training-only conservative filter research.

No network calls, broker orders, or live trading.
Never use this module to certify profitable predictions.
"""

import math

from indicators import calculate_indicators
from research.stage31_cached_signals import CachedSignalResearch
from research.stage35_accuracy_audit import wilson_interval
from scripts.run_stage30_filter_research import choose_candidate
from scripts.run_stage36_walk_forward import score_window


CANDIDATES = (
    "baseline",
    "trend",
    "rsi",
    "trend_rsi",
    "rsi_weak_trend",
    "rsi_low_volatility",
)

BREAK_EVEN_MINIMUM = 100


def passes_regime_filter(signal, row, variant):
    """Fixed research hypotheses. No fitted thresholds."""

    if signal not in ("UP", "DOWN"):
        return "NO TRADE"

    if variant not in (
        "rsi_weak_trend",
        "rsi_low_volatility",
    ):
        raise ValueError("Unknown regime filter")

    try:
        close = float(row["Close"])
        atr = float(row["ATR_14"])
        ema20 = float(row["EMA_20"])
        ema50 = float(row["EMA_50"])
    except (KeyError, ValueError, TypeError):
        return "NO TRADE"

    values = (close, atr, ema20, ema50)

    if not all(math.isfinite(x) for x in values):
        return "NO TRADE"

    if close <= 0 or atr <= 0:
        return "NO TRADE"

    trend_strength = abs(ema20 - ema50) / atr
    atr_percent = atr / close * 100

    if variant == "rsi_weak_trend":
        return signal if trend_strength < 0.35 else "NO TRADE"

    if variant == "rsi_low_volatility":
        return signal if atr_percent < 0.05 else "NO TRADE"

    return "NO TRADE"


def make_signal_fn(cache, variant):
    if variant not in CANDIDATES:
        raise ValueError("Unsupported strategy candidate")

    def signal_fn(prefix):
        if variant in (
            "baseline",
            "trend",
            "rsi",
            "trend_rsi",
        ):
            return cache.signal(prefix, variant)

        # RSI is the existing base strategy.
        signal = cache.signal(prefix, "rsi")

        if signal == "NO TRADE":
            return "NO TRADE"

        # Calculate indicators on the prefix only.
        # Later test candles cannot enter this calculation.
        indicators = calculate_indicators(prefix.copy())

        return passes_regime_filter(
            signal,
            indicators.iloc[-1],
            variant,
        )

    return signal_fn


def run_training_research(
    candles,
    train_end=720,
    payout=0.80,
    min_training_trades=30,
):
    """Training data only; the later section is not evaluated."""

    if type(train_end) is not int or train_end < 100:
        raise ValueError("Training window too small")

    if train_end > len(candles):
        raise ValueError("Training window exceeds available data")

    if not 0 < payout <= 1:
        raise ValueError("Invalid payout")

    if min_training_trades < 30:
        raise ValueError("Minimum 30 resolved trades required")

    # Critical isolation: discard all later candles BEFORE
    # creating caches or computing any indicators.
    training = candles.iloc[:train_end].copy().reset_index(drop=True)

    cache = CachedSignalResearch(training)

    summaries = {}

    for variant in CANDIDATES:
        scored = score_window(
            training,
            make_signal_fn(cache, variant),
            start=59,
            end=len(training),
            payout=payout,
        )

        summaries[variant] = scored["stats"]

    # Provisional training-only candidate.
    provisional = choose_candidate(
        summaries,
        minimum_resolved=min_training_trades,
    )

    selected = None
    reason = "NO TRADE: no qualifying training candidate"

    if provisional is not None:
        stats = summaries[provisional]
        lower, upper = wilson_interval(
            stats["wins"],
            stats["losses"],
        )

        if stats["resolved"] < BREAK_EVEN_MINIMUM:
            reason = (
                "NO TRADE: candidate has insufficient "
                "resolved training observations"
            )
        elif lower <= stats["breakeven_win_rate"]:
            reason = (
                "NO TRADE: confidence lower bound "
                "does not exceed break-even"
            )
        else:
            # Statistical research candidate only.
            # No provider/broker validation is implied.
            selected = provisional
            reason = (
                "RESEARCH CANDIDATE ONLY: "
                "requires fresh independent validation"
            )

    return {
        "training_candles": len(training),
        "candidates": summaries,
        "provisional": provisional,
        "selected_for_future_research": selected,
        "decision": reason,
        "analysis_only": True,
        "execution_enabled": False,
        "independent_validation": False,
    }
