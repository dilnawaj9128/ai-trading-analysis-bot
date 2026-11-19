"""Fast research signal evaluation for ONE immutable historical candle dataset.

Indicators/patterns used here are causal, calculated once on an ascending
completed-candle history. Signal engine is invoked on a prefix ending at the
requested bar, never on a future bar. This object is research-only; it is NOT
an API feed validator, live market signal, or broker execution model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from indicators import calculate_indicators
from patterns.candlestick import detect_candlestick_patterns
from strategy.signal_engine import generate_signal


Variant = Literal["baseline", "trend", "rsi", "trend_rsi"]
VARIANTS = ("baseline", "trend", "rsi", "trend_rsi")


@dataclass
class CachedSignalResearch:
    """Reusable signal cache for Stage 29 backtest and Stage 30 filters.

    The callback accepts only sequential prefixes from the original dataset.
    Construct a new instance for every different dataset; do not mutate source.
    """

    candles: pd.DataFrame

    def __post_init__(self):
        raw = self.candles.copy(deep=True).reset_index(drop=True)
        if len(raw) < 60 or "timestamp" not in raw:
            raise ValueError("At least 60 timestamped candles required")
        if raw.timestamp.isna().any() or raw.timestamp.duplicated().any():
            raise ValueError("Missing or duplicate timestamps")
        if not raw.timestamp.is_monotonic_increasing:
            raise ValueError("Timestamps must be ascending")
        # Indicator algorithms are causal: EMA/RSI/MACD/ATR depend on earlier
        # bars only; rolling support/resistance uses shift(1).
        self._raw = raw
        self._enriched = calculate_indicators(raw)
        patterns = detect_candlestick_patterns(raw)
        self._enriched["Pattern_Direction"] = patterns["Pattern_Direction"].to_numpy()

    def signal(self, prefix: pd.DataFrame, variant: Variant = "baseline") -> str:
        if variant not in VARIANTS:
            raise ValueError(f"Unsupported candidate: {variant}")
        n = len(prefix)
        if n < 60 or n > len(self._raw):
            raise ValueError("Invalid prefix length")
        # Block obvious use with a different dataset (accidental cache reuse).
        if not prefix.iloc[-1][["timestamp", "Open", "High", "Low", "Close"]].equals(
            self._raw.iloc[n - 1][["timestamp", "Open", "High", "Low", "Close"]]
        ):
            raise ValueError("Prefix does not match the cached dataset")

        # No future row is passed to the existing strategy.
        snapshot = self._enriched.iloc[:n]
        result = generate_signal(
            snapshot, expiry_minutes=15, data_mode="live",
            data_quality_status="VALID",
        )["signal"]
        if result == "NO TRADE" or variant == "baseline":
            return result

        import math
        row = snapshot.iloc[-1]
        try:
            close, atr, rsi, ema20, ema50 = (
                float(row[k]) for k in
                ("Close", "ATR_14", "RSI_14", "EMA_20", "EMA_50")
            )
        except (KeyError, ValueError, TypeError):
            return "NO TRADE"
        if not all(math.isfinite(x) for x in (close, atr, rsi, ema20, ema50)) or atr <= 0:
            return "NO TRADE"

        if variant in ("trend", "trend_rsi"):
            if abs(ema20 - ema50) / atr < 0.35:
                return "NO TRADE"
            if (result == "UP" and ema20 <= ema50) or (result == "DOWN" and ema20 >= ema50):
                return "NO TRADE"
        if variant in ("rsi", "trend_rsi"):
            if result == "UP" and not 50 <= rsi <= 65:
                return "NO TRADE"
            if result == "DOWN" and not 35 <= rsi <= 50:
                return "NO TRADE"
        return result

    def for_variant(self, variant: Variant):
        if variant not in VARIANTS:
            raise ValueError(f"Unsupported candidate: {variant}")
        return lambda prefix: self.signal(prefix, variant)


def assert_prefix_parity(candles: pd.DataFrame, cache: CachedSignalResearch,
                         indices: tuple[int, ...] | None = None):
    """Fail closed if optimization changes legacy Stage 30 signals."""
    from scripts.run_stage30_filter_research import conservative_signal
    if indices is None:
        indices = tuple(sorted(set([
            59, 60, 79, 100, len(candles) // 3,
            len(candles) // 2, len(candles) - 16, len(candles) - 1,
        ])))
    for i in indices:
        if not 59 <= i < len(candles):
            continue
        prefix = candles.iloc[:i + 1].copy()
        for variant in VARIANTS:
            old = conservative_signal(prefix, variant=variant)
            new = cache.signal(prefix, variant=variant)
            if old != new:
                raise AssertionError(
                    f"Signal parity failed at bar {i}, variant {variant}: old={old}, new={new}"
                )
