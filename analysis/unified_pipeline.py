from __future__ import annotations

from typing import Any, Dict, List
from analysis.ensemble_predictor import MultiModelEnsemble
from strategy.regime_risk_filter import DecisionRiskEngine
from simulator.live_paper_ledger import PaperTradingLedger


class UnifiedTradingPipeline:
    """Runs feature extraction, ML ensemble, NO-TRADE filtering, and paper trade logging."""

    def __init__(self, db_path: str = "data/paper_trading.db", model_dir: str = "models/saved") -> None:
        self.ensemble = MultiModelEnsemble(model_dir=model_dir)
        self.risk_engine = DecisionRiskEngine(min_confidence=0.60)
        self.ledger = PaperTradingLedger(db_path=db_path)

    def run_cycle(
        self,
        symbol: str,
        expiry_minutes: int,
        candles: List[Dict[str, Any]],
        model_tag: str = "default",
        auto_record_paper: bool = True,
    ) -> Dict[str, Any]:
        if not self.ensemble.is_trained and not self.ensemble.load(model_tag):
            self.ensemble.fit(candles, horizon_bars=1)
            self.ensemble.save(model_tag)

        features_df = self.ensemble.build_features(candles)
        latest_features = features_df.iloc[-1].to_dict()
        ml_out = self.ensemble.predict_latest(candles)

        decision = self.risk_engine.evaluate(
            symbol=symbol,
            expiry_minutes=expiry_minutes,
            ml_output=ml_out,
            latest_features=latest_features,
            data_fresh=len(candles) >= 40,
            timestamp_str=str(candles[-1].get("timestamp", "")),
        )
        decision["ml_breakdown"] = ml_out["model_breakdown"]
        decision["latest_price"] = float(candles[-1]["close"])

        if auto_record_paper and decision["signal"] in ("UP", "DOWN"):
            decision["paper_trade_id"] = self.ledger.record_signal(
                symbol=symbol,
                expiry_minutes=expiry_minutes,
                signal=decision["signal"],
                confidence=decision["confidence"],
                entry_price=decision["latest_price"],
            )
        else:
            decision["paper_trade_id"] = None

        return decision
