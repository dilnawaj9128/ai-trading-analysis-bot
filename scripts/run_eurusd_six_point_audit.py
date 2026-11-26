"""Six-point evidence audit for regular EUR/USD 1m/15m research.

Read-only on all input sources: no provider HTTP, no .env/key access,
no order routing, no credit-reservation mutations, no replay, no strategy
tuning, and no synthetic outcomes counted as real.

One JSON report is written to reports/ as a NEW output artifact. The report
does not convert missing evidence into "PASS".
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_JOURNAL = Path("data/research/prospective_accuracy")
DEFAULT_PROVIDER_CAPTURES = Path("data/research/provider_captures")
DEFAULT_HISTORICAL = Path("data/historical/eurusd_1min_1day.csv")
REQUIRED_NONPUSH = 100


def _item(status, **details):
    return {"status": status, **details}


def _latest_capture(directory):
    candidates = sorted(Path(directory).glob("twelve_data_eurusd_1min_*.csv"))
    return candidates[-1] if candidates else None


def feed_evidence(*, provider_captures=DEFAULT_PROVIDER_CAPTURES, now=None):
    """Official catalog is real-time; current account entitlement is NOT attested."""
    from market_data.regular_forex_feed_evidence import classify_saved_csv
    latest = _latest_capture(provider_captures)
    if latest is None:
        return _item("PROVIDER_CLASS_VERIFIED_CAPTURE_MISSING",
                     official_catalog_feed_class="REAL_TIME",
                     account_specific_live_mode_verified=False,
                     reason="No saved regular EUR/USD provider capture found")
    try:
        observed = classify_saved_csv(latest, now=now)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return _item("SAVED_CAPTURE_INVALID",
                     official_catalog_feed_class="REAL_TIME",
                     account_specific_live_mode_verified=False,
                     error_type=type(exc).__name__)
    return _item(
        "PROVIDER_CLASS_VERIFIED_ACCOUNT_MODE_UNATTESTED",
        capture=str(latest),
        capture_sha256=observed["saved_csv_sha256"],
        candles=observed["candles"],
        candle_gaps=observed["saved_candle_gaps"],
        official_catalog_feed_class=observed["official_catalog_feed_class"],
        official_docs=observed["source_urls"],
        account_specific_live_mode_verified=False,
        reason=("Provider catalog and completed-candle quality verified. "
                "Neither original HTTP receipt nor a provider-specific account "
                "mode field establishes live entitlement for this capture."),
    )


def forward_evidence(*, journal=DEFAULT_JOURNAL, payout=0.80, min_nonpush=REQUIRED_NONPUSH):
    """Count only validated prospective observations and their matched settlements."""
    from research.real_prediction_campaign import prospective_scorecard
    if not 0 < payout <= 1:
        raise ValueError("Payout must be in (0,1]")
    if type(min_nonpush) is not int or min_nonpush < 30:
        raise ValueError("Minimum nonpush sample must be at least 30")
    base = Path(journal)
    score = prospective_scorecard(base, payout=payout)
    counts = score["counts"]
    observations = sorted((base / "observations").glob("*.json"))
    settlements = sorted((base / "settlements").glob("*.json"))
    pending = [p.name for p in observations if not (base / "settlements" / p.name).is_file()]
    n = counts["WIN"] + counts["LOSS"]
    stats = score["statistical_audit"]
    if n != stats["nonpush_outcomes"]:
        raise ValueError("Prospective scorecard sample count inconsistent")
    invalid = score["invalid_evidence"]
    # Directional performance is not measurable if all observed signals abstain.
    accuracy = _item(
        ("INVALID_FORWARD_EVIDENCE" if invalid else
         "NO_DIRECTIONAL_OUTCOMES" if n == 0 else
         "FORWARD_DESCRIPTIVE_ACCURACY_ONLY"),
        wins=counts["WIN"], losses=counts["LOSS"], pushes=counts["PUSH"],
        abstained=counts["ABSTAINED"],
        nonpush_outcomes=n,
        observed_win_rate=(counts["WIN"] / n if n else None),
        prediction_accuracy_proven=False,
        invalid_evidence_count=len(invalid),
        note="Accuracy cannot be certified solely by these observations.",
    )
    sample = _item(
        "INVALID_FORWARD_EVIDENCE" if invalid else
        "SAMPLE_TARGET_REACHED_DESCRIPTIVELY" if n >= min_nonpush else
        "INSUFFICIENT_PROSPECTIVE_DIRECTIONAL_SAMPLE",
        required_nonpush=min_nonpush,
        observed_nonpush=n,
        remaining_nonpush=max(0, min_nonpush - n),
        total_observations=len(observations),
        total_settlements=len(settlements),
        pending_observations=len(pending),
        note="Sample size alone never implies statistical independence or a profitable edge.",
    )
    prospective_pass = bool(stats["statistical_screen_passed"]) and not invalid
    profit = _item(
        "INVALID_FORWARD_EVIDENCE" if invalid else
        "EXPLORATORY_STATISTICAL_SCREEN_PASSED_NOT_PROFIT_PROOF" if prospective_pass else
        "PROFITABLE_EDGE_NOT_ESTABLISHED",
        hypothetical_payout=payout,
        break_even_win_rate=stats["break_even_nonpush_win_rate_at_payout"],
        exact_p_value=stats["one_sided_exact_pvalue_vs_break_even"],
        wilson_95pct=stats["wilson_95pct_nonpush_win_rate"],
        net_idealized_units=stats["idealized_net_units"],
        statistical_audit_status=stats["status"],
        statistical_screen_passed=prospective_pass,
        profitable_live_performance_proven=False,
        note=("Even a prospective statistical screen is not sufficient proof "
              "of achievable profit after transaction costs, dependence and execution."),
    )
    return accuracy, sample, profit


def historical_evidence(path=DEFAULT_HISTORICAL, payout=0.80):
    path = Path(path)
    if not path.is_file():
        return _item("NO_HISTORICAL_DATASET_AT_THIS_PATH")
    from scripts.run_stage55_robust_validation import build_report
    try:
        report = build_report(path, min_nonpush=REQUIRED_NONPUSH, payout=payout)
        audit = report.get("stage55", {}).get("statistical_audit")
        return _item(
            "HISTORICAL_EXPLORATORY_ONLY",
            dataset=str(path),
            candles=report["quality"]["rows"],
            nonpush=(audit["nonpush_outcomes"] if audit else 0),
            win_rate=(audit["observed_nonpush_win_rate"] if audit else None),
            statistical_status=(audit["status"] if audit else None),
            break_even=(audit["break_even_nonpush_win_rate_at_payout"] if audit else None),
            excluded_from_prospective_sample=True,
        )
    except (OSError, ValueError, TypeError, KeyError, AssertionError) as exc:
        return _item("HISTORICAL_AUDIT_FAILED", error_type=type(exc).__name__)


def simulated_monitor_policy(*, start=None):
    """Virtual 24h timeline: validates policy only, NEVER real provider uptime."""
    from dashboard.monitor_reliability import (
        MAX_AUTO_ATTEMPTS, due_for_auto_fetch, begin_attempt, end_attempt,
    )
    start = start or datetime(2026, 11, 24, 0, 0, tzinfo=timezone.utc)
    state = {
        "rdm_running": True, "rdm_monitor_approval": True,
        "rdm_attempts": 0, "rdm_fetch_in_progress": False,
        "rdm_last_req": None,
    }
    attempts = 0
    for minute in range(24 * 60 + 1):
        now = start + timedelta(minutes=minute)
        if due_for_auto_fetch(
            running=state["rdm_running"], consent=state["rdm_monitor_approval"],
            attempts=state["rdm_attempts"],
            in_progress=state["rdm_fetch_in_progress"],
            last_attempt_utc=state["rdm_last_req"],
            cadence_minutes=1, now=now,
        ):
            if not begin_attempt(state, now=now):
                raise AssertionError("Monitor approval/attempt gate inconsistency")
            attempts += 1
            end_attempt(state, success=True)
    failure = {
        "rdm_running": True, "rdm_monitor_approval": True,
        "rdm_attempts": 0, "rdm_fetch_in_progress": False,
        "rdm_last_req": None,
    }
    if not begin_attempt(failure, now=start):
        raise AssertionError("Monitor failure test did not begin")
    end_attempt(failure, success=False)
    pass_guard = (attempts == MAX_AUTO_ATTEMPTS and
                  state["rdm_running"] is False and
                  failure["rdm_running"] is False)
    return _item(
        "VIRTUAL_24H_POLICY_TEST_PASSED_REAL_UPTIME_UNVERIFIED" if pass_guard
        else "MONITOR_POLICY_TEST_FAILED",
        simulated_hours=24, simulated_attempts=attempts,
        configured_attempt_limit=MAX_AUTO_ATTEMPTS,
        auto_stopped_on_cap=(not state["rdm_running"]),
        auto_stopped_on_failure=(not failure["rdm_running"]),
        actual_24h_provider_uptime_verified=False,
    )


def monitor_evidence(*, events_db=None):
    from dashboard.real_data_ops import (
        DEFAULT_EVENTS_DB, monitor_event_audit,
    )
    simulated = simulated_monitor_policy()
    event_stats = monitor_event_audit(db_path=events_db or DEFAULT_EVENTS_DB)
    simulated["local_event_counts"] = event_stats
    simulated["event_audit_proves_24h_uptime"] = False
    return simulated


def deployment_evidence(*, root=Path(".")):
    root = Path(root)
    paths = {
        "streamlit_entrypoint": root / "dashboard" / "app.py",
        "streamlit_runner": root / "run_dashboard.sh",
        "backend_entrypoint": root / "backend" / "stage49_server.py",
        "frontend_html": root / "frontend" / "index.html",
        "dependency_manifest": root / "requirements.txt",
    }
    present = {name: path.is_file() for name, path in paths.items()}
    available_modules = {
        name: importlib.util.find_spec(name) is not None
        for name in ("streamlit", "plotly", "pandas", "pytest")
    }
    return _item(
        "LOCAL_ENTRYPOINTS_CHECKED_PRODUCTION_NOT_DEPLOYED"
        if all(present.values()) and all(available_modules.values())
        else "LOCAL_INSTALLATION_INCOMPLETE",
        entrypoints=present,
        runtime_dependencies_available=available_modules,
        https_domain_certificate_verified=False,
        remote_public_deployment_verified=False,
        restart_recovery_under_real_load_verified=False,
        security_review_completed=False,
        note="A local source/dependency check cannot certify production deployment.",
    )


def credit_evidence(*, ledger=Path("data/api_usage/provider_credits.json.reservations.json")):
    path = Path(ledger)
    if not path.is_file():
        return {"state": "LEDGER_NOT_AVAILABLE", "outstanding_reserved": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        total = payload.get("reserved")
        if type(total) is not int or total < 0:
            raise ValueError("Invalid reservation total")
        return {
            "state": "READ_ONLY_LOCAL_ACCOUNTING",
            "outstanding_reserved": total,
            "interpretation": "Local unresolved holds, NOT verified provider charges",
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"state": "LEDGER_INVALID", "outstanding_reserved": None}


def run_audit(*, journal=DEFAULT_JOURNAL,
              provider_captures=DEFAULT_PROVIDER_CAPTURES,
              historical=DEFAULT_HISTORICAL, root=Path("."),
              payout=0.80, min_nonpush=REQUIRED_NONPUSH, now=None):
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Timezone-aware clock required")
    a, b, c = forward_evidence(journal=journal, payout=payout, min_nonpush=min_nonpush)
    report = {
        "schema_version": 1,
        "generated_at_utc": clock.astimezone(timezone.utc).isoformat(),
        "scope": "REGULAR_TWELVE_DATA_EURUSD_1MIN_15MIN_RESEARCH",
        "tasks": {
            "1_regular_eurusd_feed": feed_evidence(provider_captures=provider_captures, now=clock),
            "2_unseen_prediction_accuracy": a,
            "3_forward_sample": b,
            "4_statistical_edge": c,
            "5_long_session_monitoring": monitor_evidence(),
            "6_production_deployment": deployment_evidence(root=root),
        },
        "historical_reference_only": historical_evidence(historical, payout=payout),
        "credit_accounting_read_only": credit_evidence(),
        "claims": {
            "automated_trading": False,
            "live_signal": "NO TRADE",
            "statistically_verified_profit": False,
            "provider_requests": 0,
            "broker_orders": 0,
        },
        "result": "EVIDENCE_AUDIT_COMPLETE_NOT_PRODUCTION_CERTIFICATION",
    }
    return report


def write_report(report, out_dir):
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / (
        "eurusd_six_point_evidence_" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=directory, prefix=".eurusd_", delete=False) as h:
            temp = Path(h.name)
            json.dump(report, h, indent=2, sort_keys=True, allow_nan=False)
            h.write("\n")
            h.flush()
            os.fsync(h.fileno())
        # Never overwrite a previous audit snapshot.
        try:
            os.link(temp, file)
        except FileExistsError:
            file = directory / ("eurusd_six_point_evidence_" + os.urandom(6).hex() + ".json")
            os.link(temp, file)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return file


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    p.add_argument("--provider-captures", type=Path, default=DEFAULT_PROVIDER_CAPTURES)
    p.add_argument("--historical", type=Path, default=DEFAULT_HISTORICAL)
    p.add_argument("--out-dir", type=Path, default=Path("reports"))
    p.add_argument("--payout", type=float, default=0.80)
    p.add_argument("--minimum-sample", type=int, default=REQUIRED_NONPUSH)
    args = p.parse_args(argv)
    output = run_audit(
        journal=args.journal, provider_captures=args.provider_captures,
        historical=args.historical, payout=args.payout,
        min_nonpush=args.minimum_sample,
    )
    file = write_report(output, args.out_dir)
    for task, result in output["tasks"].items():
        print(task, "=>", result["status"])
    print("PROSPECTIVE_NONPUSH:",
          output["tasks"]["3_forward_sample"]["observed_nonpush"])
    print("LOCAL_RESERVED:",
          output["credit_accounting_read_only"]["outstanding_reserved"])
    print("REPORT:", file)
    print("NO PROVIDER REQUESTS; NO BROKER ORDERS; NO STRATEGY CHANGES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
