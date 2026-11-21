"""Unified evidence-first 15m accuracy campaign; NO orders or unattended polling.

Default is strictly offline: reconcile archived completed-candle captures and report.
An explicit --approve-up-to-two-requests is needed for one bounded live snapshot.
The local credit guard, request journals and 15m nonoverlap guard remain authoritative.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_JOURNAL = "data/research/prospective_accuracy"
DEFAULT_REPORT = "data/research/real_accuracy_campaign"


def archive_settlement_pass(journal=DEFAULT_JOURNAL):
    """Use captures already on disk; no HTTP; preserve invalid evidence as blocked."""
    from research.real_prediction_campaign import _candles, settle_pending

    base = Path(journal)
    captures = sorted((base / "captures").glob("*.csv"))
    result = {"captures_found": len(captures), "usable_captures": 0,
              "new_settlements": [], "invalid_captures": [], "pending": []}
    for source in captures:
        try:
            _, frame, _ = _candles(source)
            last_completed = frame["timestamp"].iloc[-1]
            if last_completed.to_pydatetime().astimezone(timezone.utc).timestamp() + 60 > datetime.now(timezone.utc).timestamp():
                raise ValueError("Capture includes not-yet-completed candle")
            details = settle_pending(journal=base, later_csv=source)
            result["usable_captures"] += 1
            result["new_settlements"].extend(details["settled"])
            result["pending"] = details["still_pending_or_blocked"]
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result["invalid_captures"].append({"file": source.name, "error": type(exc).__name__})
    if not captures:
        result["pending"] = [{"file": p.name, "reason": "No captured future candles"}
                             for p in sorted((base / "observations").glob("*.json"))
                             if not (base / "settlements" / p.name).exists()]
    return result


def accuracy_report(journal=DEFAULT_JOURNAL, report_dir=DEFAULT_REPORT, payout=0.80):
    from research.real_prediction_campaign import prospective_scorecard
    if not (0 < payout <= 1):
        raise ValueError("payout must be between zero and one")
    base = Path(journal)
    score = prospective_scorecard(base, payout=payout)
    observations = sorted((base / "observations").glob("*.json"))
    settled = sorted((base / "settlements").glob("*.json"))
    pending_names = sorted(p.name for p in observations if not (base / "settlements" / p.name).exists())
    counts = score["counts"]
    resolved = counts["WIN"] + counts["LOSS"]
    rate = counts["WIN"] / resolved if resolved else None
    net = round(counts["WIN"] * payout - counts["LOSS"], 8)
    # Nonindependent 15-minute observations could still be statistically dependent.
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign": "EUR/USD 1min candles; 15m hypothetical research expiry",
        "evidence": "local captured provider CSVs; broker-feed parity UNVERIFIED",
        "observations": len(observations), "settlements": len(settled),
        "pending_observations": pending_names,
        "counts": counts, "resolved_directional": resolved,
        "win_rate": rate, "payout": payout,
        "break_even_win_rate": 1 / (1 + payout),
        "hypothetical_net_units": net,
        "statistical_audit": score["statistical_audit"],
        "rejected_evidence": score["invalid_evidence"],
        "prediction_accuracy_verified": False,
        "live_signal": "NO TRADE", "broker_orders": 0,
        "caveat": "Historical holdouts are excluded. Forward samples may be dependent; price feed and execution parity are not verified.",
    }
    dest = Path(report_dir) / "latest_forward_accuracy.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, dest)
    return result, dest


def run(*, journal=DEFAULT_JOURNAL, report_dir=DEFAULT_REPORT,
        payout=0.80, approved=False, api_key=None):
    offline = archive_settlement_pass(journal)
    live = {"status": "NOT_REQUESTED", "provider_requests": 0}
    if approved:
        # A single explicit approval for this invocation; no retry loop.
        if not api_key:
            live = {"status": "BLOCKED_NO_KEY", "provider_requests": 0}
        else:
            from scripts.run_real_prediction_live_once import capture_live_once
            try:
                live = capture_live_once(api_key=api_key, approved=True, root=journal)
            except Exception as exc:
                # Exception may contain secrets; never echo raw error strings.
                live = {"status": "BLOCKED_OR_FAILED", "exception_type": type(exc).__name__,
                        "provider_request_outcome": "CHECK_ACCOUNTING_BEFORE_RETRY"}
            # A successful live snapshot may have settled pending observations.
            # Re-score offline; never make an additional provider request.
            offline_after = archive_settlement_pass(journal)
            offline["new_settlements"].extend(offline_after["new_settlements"])
            offline["pending"] = offline_after["pending"]
    score, report_path = accuracy_report(journal, report_dir, payout)
    return {"offline_settlement": offline, "live": live,
            "forward_accuracy": score, "report_path": str(report_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", default=DEFAULT_JOURNAL)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT)
    parser.add_argument("--payout", type=float, default=0.80)
    parser.add_argument("--approve-up-to-two-requests", action="store_true")
    args = parser.parse_args(argv)
    key = None
    if args.approve_up_to_two_requests:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        key = os.environ.get("TWELVE_DATA_API_KEY")
    output = run(journal=args.journal, report_dir=args.report_dir,
                 payout=args.payout, approved=args.approve_up_to_two_requests, api_key=key)
    settlement = output["offline_settlement"]
    live = output["live"]
    result = output["forward_accuracy"]
    print("ARCHIVED_CAPTURES:", settlement["captures_found"])
    print("SETTLED_FROM_ARCHIVES:", len(settlement["new_settlements"]))
    print("LIVE_STATUS:", live.get("status", "FETCHED_OR_RECORDED"))
    if "reason" in live:
        print("LIVE_BLOCK_REASON:", live["reason"])
    if "next_eligible_utc" in live:
        print("NEXT_ELIGIBLE_UTC:", live["next_eligible_utc"])
    print("FORWARD_COUNTS:", result["counts"])
    print("PENDING_OBSERVATIONS:", len(result["pending_observations"]))
    print("RESOLVED_DIRECTIONAL:", result["resolved_directional"])
    print("FORWARD_WIN_RATE:", "N/A" if result["win_rate"] is None else f'{result["win_rate"]:.2%}')
    print("BREAK_EVEN_AT_PAYOUT:", f'{result["break_even_win_rate"]:.2%}')
    print("HYPOTHETICAL_NET_UNITS:", result["hypothetical_net_units"])
    print("STATISTICAL_STATUS:", result["statistical_audit"]["status"])
    print("REPORT:", output["report_path"])
    print("NO BROKER ORDERS. NO PREDICTIVE ACCURACY CERTIFICATION.")
    # Fail closed on invalid evidence or unclear outcomes while still writing report.
    if result["rejected_evidence"] or settlement["invalid_captures"] or live.get("status") in {"BLOCKED_OR_FAILED", "BLOCKED_NO_KEY"}:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
