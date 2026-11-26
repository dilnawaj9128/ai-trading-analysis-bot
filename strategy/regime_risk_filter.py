from __future__ import annotations

from typing import Any, Dict, List


class DecisionRiskEngine:
    """Combines ML probabilities, indicator alignment, and market regime to output UP, DOWN, or NO TRADE."""

    def __init__(
        self,
        min_confidence: float = 0.60,
        min_atr_pct: float = 0.0002,
        max_atr_pct: float = 0.025,
    ) -> None:
        self.min_confidence = min_confidence
        self.min_atr_pct = min_atr_pct
        self.max_atr_pct = max_atr_pct

    def classify_regime(self, features_row: Dict[str, float]) -> str:
        atr_pct = abs(features_row.get("atr_pct", 0.0))
        ema_diff = features_row.get("ema_diff", 0.0)

        if atr_pct > self.max_atr_pct:
            return "EXTREME_VOLATILITY"
        if atr_pct < self.min_atr_pct or abs(ema_diff) < 0.00015:
            return "SIDEWAYS"
        return "TRENDING_UP" if ema_diff > 0 else "TRENDING_DOWN"

    def evaluate(
        self,
        symbol: str,
        expiry_minutes: int,
        ml_output: Dict[str, Any],
        latest_features: Dict[str, float],
        data_fresh: bool = True,
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        regime = self.classify_regime(latest_features)
        prob_up = float(ml_output["prob_up"])
        prob_down = float(ml_output["prob_down"])
        rsi_norm = float(latest_features.get("rsi_norm", 0.0))
        macd_hist = float(latest_features.get("macd_hist", 0.0))

        # 1. Data freshness guard
        if not data_fresh:
            return {
                "symbol": symbol,
                "expiry_minutes": expiry_minutes,
                "signal": "NO TRADE",
                "confidence": max(prob_up, prob_down),
                "regime": regime,
                "reasons": ["Stale or incomplete candle feed detected."],
            }

        # 2. Regime filter (Avoid choppy/sideways or spike markets)
        if regime in ("SIDEWAYS", "EXTREME_VOLATILITY"):
            return {
                "symbol": symbol,
                "expiry_minutes": expiry_minutes,
                "signal": "NO TRADE",
                "confidence": round(max(prob_up, prob_down), 4),
                "regime": regime,
                "reasons": [f"Market regime is {regime}; avoiding low-edge/high-noise conditions."],
            }

        # 3. Confidence + Indicator agreement check
        if prob_up >= self.min_confidence:
            if regime == "TRENDING_UP" and macd_hist > 0 and rsi_norm < 0.45:
                reasons.append(f"ML ensemble bullish ({prob_up:.1%}) aligned with UP trend & positive MACD.")
                return {
                    "symbol": symbol,
                    "expiry_minutes": expiry_minutes,
                    "signal": "UP",
                    "confidence": round(prob_up, 4),
                    "regime": regime,
                    "reasons": reasons,
                }
            reasons.append("Bullish ML probability lacks trend/MACD confirmation or RSI is overbought.")

        elif prob_down >= self.min_confidence:
            if regime == "TRENDING_DOWN" and macd_hist < 0 and rsi_norm > -0.45:
                reasons.append(f"ML ensemble bearish ({prob_down:.1%}) aligned with DOWN trend & negative MACD.")
                return {
                    "symbol": symbol,
                    "expiry_minutes": expiry_minutes,
                    "signal": "DOWN",
                    "confidence": round(prob_down, 4),
                    "regime": regime,
                    "reasons": reasons,
                }
            reasons.append("Bearish ML probability lacks trend/MACD confirmation or RSI is oversold.")
        else:
            reasons.append(
                f"Model confidence below threshold ({max(prob_up, prob_down):.1%} < {self.min_confidence:.0%})."
            )

        return {
            "symbol": symbol,
            "expiry_minutes": expiry_minutes,
            "signal": "NO TRADE",
            "confidence": round(max(prob_up, prob_down), 4),
            "regime": regime,
            "reasons": reasons,
        }
