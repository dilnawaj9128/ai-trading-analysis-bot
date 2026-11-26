from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
from analysis.ensemble_predictor import MultiModelEnsemble
from strategy.regime_risk_filter import DecisionRiskEngine
from simulator.live_paper_ledger import PaperTradingLedger


def _two_sided_binomial_pvalue(wins: int, n: int, p0: float = 0.5) -> float:
    """Exact two-sided binomial p-value against p0 (default 50% coin-flip baseline)."""
    if n <= 0:
        return 1.0
    pmf = [math.comb(n, k) * (p0 ** k) * ((1.0 - p0) ** (n - k)) for k in range(n + 1)]
    obs_prob = pmf[wins]
    p_val = sum(prob for prob in pmf if prob <= obs_prob + 1e-15)
    return round(min(1.0, p_val), 6)


class ForwardAccuracyProver:
    """Runs strictly non-lookahead sequential forward testing and computes accuracy proof metrics."""

    def __init__(
        self,
        db_path: str = "data/paper_trading.db",
        model_dir: str = "models/saved",
        min_confidence: float = 0.60,
        warmup_bars: int = 45,
        retrain_every: int = 10,
    ) -> None:
        self.ledger = PaperTradingLedger(db_path=db_path)
        self.model_dir = model_dir
        self.min_confidence = min_confidence
        self.warmup_bars = warmup_bars
        self.retrain_every = max(1, retrain_every)

    def run_forward_proof(
        self,
        symbol: str,
        expiry_minutes: int,
        candles: List[Dict[str, Any]],
        horizon_bars: int = 1,
        stake: float = 100.0,
        payout_ratio: float = 0.80,
        report_path: Optional[str] = "data/research/forward_accuracy_proof.json",
    ) -> Dict[str, Any]:
        min_required = self.warmup_bars + horizon_bars + 5
        if len(candles) < min_required:
            raise ValueError(f"Need at least {min_required} candles; got {len(candles)}.")

        ensemble = MultiModelEnsemble(model_dir=self.model_dir)
        risk_engine = DecisionRiskEngine(min_confidence=self.min_confidence)

        total_evaluated = 0
        no_trade_count = 0
        trades_log: List[Dict[str, Any]] = []

        # Strict no-lookahead loop: at step i, only candles[: i + 1] are visible
        for i in range(self.warmup_bars, len(candles) - horizon_bars):
            visible_candles = candles[: i + 1]
            # Train/update only on candles strictly prior to current decision bar i
            if not ensemble.is_trained or (i - self.warmup_bars) % self.retrain_every == 0:
                ensemble.fit(visible_candles[:-1], horizon_bars=horizon_bars)

            feat_row = ensemble.build_features(visible_candles).iloc[-1].to_dict()
            ml_pred = ensemble.predict_latest(visible_candles)
            decision = risk_engine.evaluate(
                symbol=symbol,
                expiry_minutes=expiry_minutes,
                ml_output=ml_pred,
                latest_features=feat_row,
                data_fresh=len(visible_candles) >= self.warmup_bars,
            )

            total_evaluated += 1
            sig = decision["signal"]
            if sig not in ("UP", "DOWN"):
                no_trade_count += 1
                continue

            entry_price = float(candles[i]["close"])
            exit_price = float(candles[i + horizon_bars]["close"])
            trade_id = self.ledger.record_signal(
                symbol=symbol,
                expiry_minutes=expiry_minutes,
                signal=sig,
                confidence=decision["confidence"],
                entry_price=entry_price,
                stake=stake,
                payout_ratio=payout_ratio,
            )
            settled = self.ledger.settle_trade(int(trade_id), exit_price=exit_price)
            trades_log.append(
                {
                    "trade_id": trade_id,
                    "timestamp": candles[i].get("timestamp"),
                    "signal": sig,
                    "confidence": decision["confidence"],
                    "regime": decision["regime"],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "outcome": settled["status"],
                    "pnl": settled["pnl"],
                }
            )

        decided = [t for t in trades_log if t["outcome"] in ("WIN", "LOSS")]
        wins = sum(1 for t in decided if t["outcome"] == "WIN")
        losses = sum(1 for t in decided if t["outcome"] == "LOSS")
        n_decided = len(decided)
        accuracy = round(wins / n_decided, 4) if n_decided > 0 else 0.0
        no_trade_rate = round(no_trade_count / total_evaluated, 4) if total_evaluated > 0 else 0.0
        net_pnl = round(sum(float(t["pnl"]) for t in trades_log), 2)

        # Max drawdown on cumulative PnL curve
        cum_pnl = 0.0
        peak_pnl = 0.0
        max_dd = 0.0
        for t in trades_log:
            cum_pnl += float(t["pnl"])
            if cum_pnl > peak_pnl:
                peak_pnl = cum_pnl
            dd = peak_pnl - cum_pnl
            if dd > max_dd:
                max_dd = dd

        p_value = _two_sided_binomial_pvalue(wins=wins, n=n_decided, p0=0.5)
        statistically_significant = bool(n_decided >= 15 and accuracy > 0.55 and p_value < 0.05)

        proof_report: Dict[str, Any] = {
            "symbol": symbol,
            "expiry_minutes": expiry_minutes,
            "horizon_bars": horizon_bars,
            "bars_evaluated": total_evaluated,
            "signals_taken": len(trades_log),
            "no_trade_filtered": no_trade_count,
            "no_trade_rate": no_trade_rate,
            "wins": wins,
            "losses": losses,
            "accuracy_win_rate": accuracy,
            "net_pnl": net_pnl,
            "max_drawdown": round(max_dd, 2),
            "p_value_vs_50pct": p_value,
            "statistically_significant_edge": statistically_significant,
            "verdict": (
                "STATISTICAL_EDGE_SUPPORTED"
                if statistically_significant
                else "INSUFFICIENT_OR_UNPROVEN_EDGE_KEEP_PAPER_TESTING"
            ),
            "trades": trades_log[-25:],
        }

        if report_path:
            out_file = Path(report_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps(proof_report, indent=2), encoding="utf-8")

        return proof_report
