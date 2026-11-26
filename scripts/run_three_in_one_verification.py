"""One-shot 3-in-1 LOCAL regular EUR/USD research workflow.

Workflows:
 1. Reconcile existing provider captures to prior forward observations;
    optionally collect ONE real prospective capture through the existing
    guarded, user-initiated authorization (no loop or automatic retries).
 2. Reconcile ONLY cryptographically/receipt-verified reservations and
    separately classify every remaining reserved request read-only.
 3. Ephemeral loopback-only HTTP and Streamlit deployment smoke test.

The live fetch is disabled by default. --one-live-fetch uses the existing
authorization, quota and nonoverlap guards. It may consume at most TWO
provider requests. If authorization is denied, do not retry.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_accuracy_all import archive_settlement_pass
from research.real_prediction_campaign import prospective_scorecard
from scripts.run_reservation_evidence_audit import audit as reservation_audit
from scripts.local_deployment_smoke import deployment_smoke
from market_data.provider_credit_state import DEFAULT_PATH

JOURNAL = Path("data/research/prospective_accuracy")
OUTPUT = Path("reports")


def _safe_reconcile():
    """May settle only request-bound verified historical success records."""
    from market_data.verified_reservation_settlement import reconcile_verified_historical
    try:
        return reconcile_verified_historical()
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        return {"status": "VERIFIED_RECONCILIATION_BLOCKED",
                "error_type": type(exc).__name__,
                "unsafe_reservations_not_released": True}


def _safe_reservation_audit():
    """Read-only snapshot; called before AND after an optional HTTP attempt."""
    try:
        return reservation_audit(Path(DEFAULT_PATH))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"status": "RESERVATION_EVIDENCE_AUDIT_BLOCKED",
                "error_type": type(exc).__name__}


def run(*, journal=JOURNAL, output=OUTPUT, one_live_fetch=False,
        api_key=None, smoke=True):
    # No new network unless this invocation was explicitly given the one-shot flag.
    credit_result = _safe_reconcile()
    reservations_before = _safe_reservation_audit()
    try:
        archived = archive_settlement_pass(journal)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        archived = {"status": "ARCHIVED_SETTLEMENT_BLOCKED",
                    "error_type": type(exc).__name__}
    live = {"status": "NOT_REQUESTED", "requests_authorized": 0}
    if one_live_fetch:
        if not api_key:
            live = {"status": "BLOCKED_API_KEY_MISSING", "no_automatic_retry": True}
        else:
            try:
                from scripts.run_real_prediction_live_once import capture_live_once
                # Authorizes at most 2 requests and honors existing credit/observation safeguards.
                live = capture_live_once(api_key=api_key, approved=True, root=journal)
            except Exception as exc:
                # Third-party exception text could contain secrets: never emit it.
                live = {"status": "LIVE_REQUEST_FAILED_OR_BLOCKED",
                        "error_type": type(exc).__name__,
                        "request_accounting_must_be_inspected_before_any_retry": True}
            # On successful capture, the existing capture runner handles prospective
            # observation and settlement before returning; do not send more HTTP.
    # Re-read after a failed/uncertain request. Pre-attempt credit snapshots
    # MUST NOT be shown as current: a transport exception may reserve a credit.
    reservations_after = _safe_reservation_audit()
    try:
        prospective = prospective_scorecard(journal)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        prospective = {"status": "PROSPECTIVE_SCORECARD_BLOCKED",
                       "error_type": type(exc).__name__}
    deployment = deployment_smoke() if smoke else {
        "status": "SKIPPED", "remote_production_deployment_verified": False}
    counts = prospective.get("counts") or {}
    n = counts.get("WIN", 0) + counts.get("LOSS", 0)
    report = {
        "schema": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "REGULAR_EURUSD_1MIN_15MIN_RESEARCH_ONLY",
        "task_1_forward_collection": {
            "archived_settlement_pass": archived,
            "bounded_live_attempt": live,
            "prospective_counts": counts,
            "prospective_nonpush": n,
            "minimum_nonpush_target": 100,
            "prospective_target_met": n >= 100,
            "accuracy_proven": False,
            "statistical_audit": prospective.get("statistical_audit"),
        },
        "task_2_receipt_bound_credit_review": {
            "verified_reconciliation": credit_result,
            "read_only_reservation_evidence_before_attempt": reservations_before,
            "read_only_reservation_evidence": reservations_after,
            "no_ledger_reset_or_unverified_release": True,
        },
        "task_3_local_deployment": deployment,
        "limitations": [
            "Historical results do not count as prospective observations.",
            "A successful virtual or localhost test is not real 24h uptime.",
            "Broker-feed price parity and future profitability remain unverified.",
            "A live request may spend up to two credits; failed/uncertain attempts must not be retried.",
        ],
        "live_trade_signal": "NO TRADE",
        "broker_orders": 0,
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    filename = output / ("three_in_one_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output, prefix=".three_in_one_", delete=False) as f:
            tmp = Path(f.name)
            json.dump(report, f, indent=2, sort_keys=True, allow_nan=False, default=str)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        # create-only, never overwrite an earlier report
        try:
            os.link(tmp, filename)
        except FileExistsError:
            filename = output / ("three_in_one_" + os.urandom(6).hex() + ".json")
            os.link(tmp, filename)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return report, filename


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--one-live-fetch", action="store_true",
                   help="Opt-in ONE guarded prospective fetch: maximum two accounted requests")
    p.add_argument("--no-local-smoke", action="store_true")
    p.add_argument("--journal", type=Path, default=JOURNAL)
    p.add_argument("--out-dir", type=Path, default=OUTPUT)
    args = p.parse_args(argv)
    key = None
    if args.one_live_fetch:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        key = os.environ.get("TWELVE_DATA_API_KEY")
    report, file = run(journal=args.journal, output=args.out_dir,
                       one_live_fetch=args.one_live_fetch, api_key=key,
                       smoke=not args.no_local_smoke)
    a = report["task_1_forward_collection"]
    b = report["task_2_receipt_bound_credit_review"]
    c = report["task_3_local_deployment"]
    print("LIVE:", a["bounded_live_attempt"].get("status"))
    print("ARCHIVE:", a["archived_settlement_pass"].get("status", "OFFLINE_PASS_FINISHED"))
    print("FORWARD_COUNTS:", a["prospective_counts"])
    print("PROSPECTIVE_NONPUSH:", a["prospective_nonpush"], "/ 100")
    print("CREDIT_RECONCILIATION:", b["verified_reconciliation"].get("status"))
    print("OUTSTANDING_RESERVED:", b["read_only_reservation_evidence"].get("outstanding_reserved"))
    print("DEPLOYMENT_SMOKE:", c["status"])
    print("REPORT:", file)
    print("NO BROKER ORDERS; NO AUTOMATIC HTTP RETRIES; NO REAL-PROFIT CLAIM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
