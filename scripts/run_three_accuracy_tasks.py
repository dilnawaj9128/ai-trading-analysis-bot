"""One entrypoint: source quality, safe 15m forward collection and accuracy.

Offline by default. Explicit approval permits ONE existing guarded live workflow
(max two accounted HTTP requests). Never executes trades or verifies broker parity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify_captures(journal="data/research/prospective_accuracy"):
    from research.real_prediction_campaign import _candles, utc, ONE_MINUTE
    from datetime import datetime, timezone
    result = {"source": "LOCAL_SAVED_CSV", "market_data_quality": "NO_CAPTURES",
              "valid_captures": 0, "invalid_captures": [],
              "provider_feed_mode_verified": False,
              "quotex_price_parity_verified": False,
              "directional_live_signal_allowed": False}
    captures = sorted((Path(journal) / "captures").glob("*.csv"))
    if captures:
        result["market_data_quality"] = "PASS"
    for capture in captures:
        try:
            _, df, quality = _candles(capture)
            if utc(df["timestamp"].iloc[-1]) + ONE_MINUTE > datetime.now(timezone.utc):
                raise ValueError("Incomplete last candle")
            result["valid_captures"] += 1
        except (ValueError, OSError, KeyError, TypeError) as exc:
            result["invalid_captures"].append({"capture": capture.name, "error_type": type(exc).__name__})
    if result["invalid_captures"]:
        result["market_data_quality"] = "FAIL"
    # Local CSVs cannot establish provider execution feed mode or Quotex parity.
    return result


def run(*, journal="data/research/prospective_accuracy",
        report_dir="data/research/real_accuracy_campaign", approved=False):
    from scripts.run_accuracy_all import run as existing_run
    # Audit before and after bounded live workflow. The existing authorization
    # and non-overlap guards remain authoritative; never bypass them.
    before = verify_captures(journal)
    key = None
    if approved:
        import os
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        key = os.environ.get("TWELVE_DATA_API_KEY")
    campaign = existing_run(journal=journal, report_dir=report_dir,
                            approved=approved, api_key=key)
    after = verify_captures(journal)
    score = campaign["forward_accuracy"]
    result = {"schema": 1,
              "task_1_data_verification": after,
              "task_2_forward_testing": {
                  "approved_live_attempt": approved,
                  "live_status": campaign["live"].get("status", "FETCHED_OR_RECORDED"),
                  "pending": len(score["pending_observations"]),
                  "archived_before": before["valid_captures"],
                  "archived_after": after["valid_captures"],
                  "settled_from_existing_archives": len(campaign["offline_settlement"]["new_settlements"]),
              },
              "task_3_accuracy": {
                  "counts": score["counts"],
                  "resolved_directional": score["resolved_directional"],
                  "win_rate": score["win_rate"],
                  "break_even_win_rate": score["break_even_win_rate"],
                  "hypothetical_net_units": score["hypothetical_net_units"],
                  "statistical_status": score["statistical_audit"]["status"],
                  "accuracy_verified": False,
              },
              "broker_orders": 0,
              "report_path": campaign["report_path"]}
    dest = Path(report_dir) / "latest_three_tasks.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-up-to-two-requests", action="store_true")
    args = parser.parse_args()
    result = run(approved=args.approve_up_to_two_requests)
    print("DATA_QUALITY:", result["task_1_data_verification"]["market_data_quality"])
    print("VALID_CAPTURES:", result["task_1_data_verification"]["valid_captures"])
    print("QUOTEX_PARITY_VERIFIED: False")
    print("LIVE_STATUS:", result["task_2_forward_testing"]["live_status"])
    print("PENDING:", result["task_2_forward_testing"]["pending"])
    print("COUNTS:", result["task_3_accuracy"]["counts"])
    print("DIRECTIONAL_OUTCOMES:", result["task_3_accuracy"]["resolved_directional"])
    print("WIN_RATE:", result["task_3_accuracy"]["win_rate"])
    print("STATISTICAL_STATUS:", result["task_3_accuracy"]["statistical_status"])
    print("REPORT:", result["report_path"])
    print("FULL_REPORT: data/research/real_accuracy_campaign/latest_three_tasks.json")
    if result["task_1_data_verification"]["market_data_quality"] == "FAIL":
        return 2
    if result["task_2_forward_testing"]["live_status"] in {"BLOCKED_OR_FAILED", "BLOCKED_NO_KEY"}:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
