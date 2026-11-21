"""Stage 57 read-only diagnostic for prospective 15m research evidence.

No HTTP, API keys, orders, new observations, settlements, or strategy changes.
Reports the reason for saved NO TRADE decisions only when their exact original
decision candle is available in a validated archived capture.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.real_prediction_campaign import _load_envelope, _candles, utc

MINUTE = timedelta(minutes=1)


def diagnose(journal="data/research/prospective_accuracy"):
    from indicators import calculate_indicators
    from patterns.candlestick import detect_candlestick_patterns
    from strategy.signal_engine import generate_signal

    root = Path(journal)
    capture_info = []
    for capture in sorted((root / "captures").glob("*.csv")):
        try:
            _, frame, _ = _candles(capture)
            capture_info.append((capture, frame))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            capture_info.append((capture, None))

    results = []
    reasons = Counter()
    invalid = 0
    for path in sorted((root / "observations").glob("*.json")):
        try:
            obs = _load_envelope(path, "OBSERVATION")
            decision = utc(obs["decision_time_utc"])
            expiry = utc(obs["expiry_time_utc"])
            if expiry != decision + timedelta(minutes=15):
                raise ValueError("Invalid 15-minute expiry")
            observed = utc(obs["recorded_at_utc"])
            if observed < decision or observed >= expiry:
                raise ValueError("Invalid observation timing")
            expected_open = decision - MINUTE
            match = None
            settlement_sources = []
            for source, frame in capture_info:
                if frame is None:
                    continue
                subset = frame.loc[frame["timestamp"] <= expected_open]
                exact = subset.loc[subset["timestamp"] == expected_open]
                if len(exact) == 1 and math.isclose(
                    float(exact.iloc[0]["Close"]), float(obs["entry_reference_close"]),
                    rel_tol=0, abs_tol=1e-10
                ) and len(subset) >= 90:
                    if match is None:
                        match = (source, subset.copy())
                expiry_open = expiry - MINUTE
                target = frame.loc[frame["timestamp"] == expiry_open]
                initial = frame.loc[frame["timestamp"] == expected_open]
                if len(target) == 1 and len(initial) == 1 and math.isclose(
                    float(initial.iloc[0]["Close"]), float(obs["entry_reference_close"]),
                    rel_tol=0, abs_tol=1e-10
                ):
                    settlement_sources.append(source.name)
            settled_path = root / "settlements" / path.name
            record = {
                "observation": path.name,
                "decision_utc": decision.isoformat(),
                "expiry_utc": expiry.isoformat(),
                "hypothesis": obs["research_hypothesis"],
                "status": "SETTLED" if settled_path.exists() else "PENDING",
                "matching_settlement_captures": settlement_sources,
                "no_trade_reason": "NOT_EVALUATED",
            }
            if settled_path.exists():
                settlement = _load_envelope(settled_path, "SETTLEMENT")
                if settlement["observation_sha256"] != __import__("research.real_prediction_campaign", fromlist=["digest"]).digest(obs):
                    raise ValueError("Settlement checksum mismatch")
                record["outcome"] = settlement["result"]
            elif not settlement_sources:
                record["pending_reason"] = "NO_CAPTURE_WITH_EXACT_ENTRY_AND_EXPIRY_CLOSE"
            else:
                record["pending_reason"] = "CAPTURE_AVAILABLE_REVIEW_SETTLEMENT_GUARDS"
            if obs["research_hypothesis"] == "NO TRADE" and match is not None:
                _, prefix = match
                enriched = calculate_indicators(prefix)
                patterns = detect_candlestick_patterns(prefix)
                if "Pattern_Direction" in patterns.columns:
                    enriched["Pattern_Direction"] = patterns["Pattern_Direction"].to_numpy()
                analysis = generate_signal(
                    enriched, expiry_minutes=15, data_mode="live",
                    data_quality_status="VALID"
                )
                record["offline_recomputed_hypothesis"] = analysis["signal"]
                if analysis["signal"] == "NO TRADE":
                    record["no_trade_reason"] = analysis["reasons"][-1]
                    reasons[record["no_trade_reason"]] += 1
                else:
                    record["no_trade_reason"] = "RECOMPUTED_SIGNAL_MISMATCH_REVIEW"
            elif obs["research_hypothesis"] == "NO TRADE":
                record["no_trade_reason"] = "ORIGINAL_PREFIX_NOT_FOUND"
            results.append(record)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            invalid += 1
            results.append({"observation": path.name, "status": "INVALID_EVIDENCE", "error_type": type(exc).__name__})
    return {
        "stage": 57, "mode": "READ_ONLY_OFFLINE_DIAGNOSTIC",
        "captures": len(capture_info),
        "invalid_captures": [p.name for p, frame in capture_info if frame is None],
        "observations": results, "invalid_observations": invalid,
        "no_trade_reasons": dict(reasons),
        "no_http_requests": True, "broker_orders": 0,
        "strategy_changed": False,
        "prediction_accuracy_verified": False, "live_signal": "NO TRADE",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", default="data/research/prospective_accuracy")
    args = parser.parse_args(argv)
    report = diagnose(args.journal)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["invalid_observations"] or report["invalid_captures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
