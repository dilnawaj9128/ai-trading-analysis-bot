from __future__ import annotations

from typing import Any, Dict, List
from analysis.ensemble_predictor import MultiModelEnsemble
from simulator.live_paper_ledger import PaperTradingLedger


class DriftAutoRetrainer:
    """Triggers ensemble retraining when paper trading drift is detected."""

    def __init__(
        self,
        ledger: PaperTradingLedger,
        model_dir: str = "models/saved",
        min_candles_to_retrain: int = 50,
    ) -> None:
        self.ledger = ledger
        self.model_dir = model_dir
        self.min_candles_to_retrain = min_candles_to_retrain

    def check_and_retrain(
        self,
        candles: List[Dict[str, Any]],
        horizon_bars: int = 1,
        force: bool = False,
    ) -> Dict[str, Any]:
        stats = self.ledger.get_performance_and_drift()
        drift_active = bool(stats.get("drift_detected", False))

        if not (drift_active or force):
            return {
                "retrained": False,
                "reason": "No drift detected.",
                "drift_stats": stats,
            }

        if len(candles) < self.min_candles_to_retrain:
            return {
                "retrained": False,
                "reason": f"Insufficient candles ({len(candles)} < {self.min_candles_to_retrain}).",
                "drift_stats": stats,
            }

        ensemble = MultiModelEnsemble(model_dir=self.model_dir)
        metrics = ensemble.fit(candles, horizon_bars=horizon_bars)
        return {
            "retrained": True,
            "reason": "Forced retrain." if force else "Drift detected -> model retrained and saved.",
            "drift_stats": stats,
            "training_metrics": metrics,
        }
