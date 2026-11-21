"""One-shot, bounded research A/B campaign. Not an unattended poller.

1. Reconcile already archived captures.
2. Optionally make ONE explicitly approved, guarded provider snapshot.
3. Record 0.25/0.50 ATR paired hypotheses from that fresh snapshot only.
4. Independently settle exact 15m outcomes and report both arms.

No broker orders. The original strategy and safety checks are untouched.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from scripts import run_atr_forward_compare as ab
from scripts.run_accuracy_all import run as run_existing

CAPTURES = Path("data/research/prospective_accuracy/captures")
JOURNAL = Path("data/research/atr_forward_comparison")
OUTPUT = Path("data/research/real_accuracy_campaign/latest_atr_campaign.json")
ALLOWED_LIVE_STATUSES = {None, "FETCHED_OR_RECORDED", "CAPTURE_SAVED_OBSERVATION_DEFERRED"}


def run(*, approved=False, capture_dir=CAPTURES, journal=JOURNAL, output=OUTPUT):
    from datetime import datetime, timezone
    existing_before = set(Path(capture_dir).glob("*.csv"))
    new_settlements = []
    for source in sorted(existing_before):
        new_settlements.extend(ab.settle(source, journal=journal))

    key = None
    if approved:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        key = os.environ.get("TWELVE_DATA_API_KEY")

    # Existing bounded authorization and account reconciliation are authoritative.
    campaign = run_existing(approved=approved, api_key=key)
    live = campaign["live"]
    live_status = live.get("status", "FETCHED_OR_RECORDED")
    new_files = set(Path(capture_dir).glob("*.csv")) - existing_before

    for source in sorted(new_files):
        new_settlements.extend(ab.settle(source, journal=journal))

    paired = None
    paired_state = "NO_NEW_PROSPECTIVE_CANDLES"
    if approved and live_status not in {"BLOCKED_NO_HTTP", "BLOCKED_NO_KEY", "BLOCKED_OR_FAILED"}:
        saved = live.get("saved_csv")
        if saved and Path(saved) in new_files:
            try:
                target, observation = ab.record(saved, journal=journal)
                paired = {"path": str(target), "signals": observation["models"],
                          "decision_utc": observation["decision_utc"],
                          "expiry_utc": observation["expiry_utc"]}
                paired_state = "RECORDED"
            except (ValueError, FileExistsError) as exc:
                # No retry or forged prediction; no raw network exception strings.
                paired_state = "SKIPPED_" + type(exc).__name__.upper()
        else:
            paired_state = "NO_NEW_SAVED_CAPTURE"
    elif approved:
        paired_state = "FETCH_BLOCKED_NO_PAIRED_PREDICTION"

    stats = ab.report(journal=journal)
    outcome = {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "live_fetch_status": live_status,
        "live_block_reason": live.get("reason", "NOT_REPORTED"),
        "approval": approved,
        "new_saved_captures": len(new_files),
        "new_paired_settlements": len(new_settlements),
        "pair_recording_status": paired_state,
        "new_pair": paired,
        "control_vs_challenger": stats,
        "previous_campaign": {
            "pending": len(campaign["forward_accuracy"]["pending_observations"]),
            "directional_outcomes": campaign["forward_accuracy"]["resolved_directional"],
            "counts": campaign["forward_accuracy"]["counts"],
        },
        "no_broker_orders": True,
        "broker_parity_verified": False,
        "accuracy_certified": False,
        "note": "Prospective only. Each invocation with approval can consume up to two provider API credits. Do not retry failed/uncertain requests.",
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".json.tmp")
    temp.write_text(json.dumps(outcome, sort_keys=True, indent=2) + "\n")
    os.replace(temp, destination)
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-up-to-two-requests", action="store_true")
    args = parser.parse_args(argv)
    result = run(approved=args.approve_up_to_two_requests)
    print("LIVE_FETCH_STATUS:", result["live_fetch_status"])
    print("LIVE_BLOCK_REASON:", result["live_block_reason"])
    print("NEW_SAVED_CAPTURES:", result["new_saved_captures"])
    print("NEW_PAIRED_SETTLEMENTS:", result["new_paired_settlements"])
    print("PAIR_RECORDING:", result["pair_recording_status"])
    if result["new_pair"]:
        print("NEW_PAIR_SIGNALS:", result["new_pair"]["signals"])
        print("NEW_PAIR_EXPIRY_UTC:", result["new_pair"]["expiry_utc"])
    s = result["control_vs_challenger"]
    print("PAIRS_RECORDED:", s["pairs_recorded"])
    print("PAIRS_SETTLED:", s["pairs_settled"])
    for name, value in s["arms"].items():
        print(name.upper(), ":", value)
    print("BREAK_EVEN_WIN_RATE:", f'{s["break_even"]:.2%}')
    print("COMPARISON_STATUS:", s["comparison_status"])
    print("REPORT:", OUTPUT)
    print("NO BROKER ORDERS / NO VERIFIED QUOTEX ACCURACY")
    if result["live_fetch_status"] in {"BLOCKED_OR_FAILED", "BLOCKED_NO_KEY"}:
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
