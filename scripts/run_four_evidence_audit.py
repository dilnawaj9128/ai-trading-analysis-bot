"""Truthful combined prospective accuracy, edge, live uptime and deployment audit.

Default: offline-only. Never hits the market data provider or a broker.
Optional --local-health-url starts a foreground, timestamped local  health
session for a chosen duration; --production-health-url checks a supplied HTTPS
deployment endpoint. Does NOT deploy an application or imply production uptime.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from research.real_prediction_campaign import prospective_scorecard
from scripts.run_accuracy_all import archive_settlement_pass

JOURNAL = Path("data/research/prospective_accuracy")
REPORTS = Path("reports")


def utc_stamp():
    return datetime.now(timezone.utc).isoformat()


def health_once(url):
    try:
        req = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read(100_000))
            return (
                response.status == 200
                and type(data) is dict
                and data.get("status") == "ONLINE"
                and data.get("trading_execution_enabled") is False
            )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def local_monitor(*, health_url=None, duration_seconds=0, interval_seconds=30,
                  sleeper=time.sleep, clock=time.monotonic, probe=health_once):
    if health_url is None:
        return {"status": "NOT_RUN", "actual_uptime_verified": False,
                "observed_seconds": 0, "samples": 0}
    parsed = urlsplit(health_url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("Long-session monitor only accepts an explicit localhost HTTP health URL")
    if type(duration_seconds) is not int or not 60 <= duration_seconds <= 86400:
        raise ValueError("Monitoring duration must be 60..86400 real seconds")
    if type(interval_seconds) is not int or not 5 <= interval_seconds <= 600:
        raise ValueError("Monitoring interval must be 5..600 real seconds")
    start = clock()
    samples = []
    while True:
        when = utc_stamp()
        ok = bool(probe(health_url))
        samples.append({"observed_at_utc": when, "health_ok": ok})
        elapsed = clock() - start
        if elapsed >= duration_seconds or not ok:
            break
        sleeper(min(interval_seconds, duration_seconds - elapsed))
    duration = max(0, clock() - start)
    all_good = all(item["health_ok"] for item in samples)
    reached = duration >= duration_seconds
    return {
        "status": "HEALTH_SESSION_PASSED" if all_good and reached else "HEALTH_SESSION_INCOMPLETE_OR_FAILED",
        "actual_uptime_verified": all_good and reached,
        "observed_seconds": round(duration, 2),
        "requested_seconds": duration_seconds,
        "samples": len(samples), "sample_history": samples,
        "continuous_uptime_proven": False,
        "real_24h_uptime_verified": all_good and reached and duration_seconds == 86400,
        "note": "Sampled health checks verify responses at sample times; no continuous-availability guarantee.",
    }


def production_check(*, health_url=None, probe=health_once):
    if health_url is None:
        return {"status": "NOT_DEPLOYED_OR_NOT_CHECKED",
                "remote_production_deployment_verified": False}
    parsed = urlsplit(health_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Production verification requires a public HTTPS URL without credentials or fragments")
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Production URL cannot be localhost")
    healthy = bool(probe(health_url))
    return {
        "status": "REMOTE_HTTPS_HEALTH_PASSED" if healthy else "REMOTE_HTTPS_HEALTH_FAILED",
        "remote_production_deployment_verified": healthy,
        "real_24h_uptime_verified": False,
        "caveat": "An HTTPS health response proves point-in-time reachability only, not secure production readiness.",
    }


def run(*, journal=JOURNAL, settle_archives=True,
        local_health_url=None, monitor_seconds=0,
        production_health_url=None):
    # A completed observation cannot be fabricated after expiry.
    archives = archive_settlement_pass(journal) if settle_archives else {"status": "SKIPPED"}
    score = prospective_scorecard(journal)
    stats = score["statistical_audit"]
    invalid = score["invalid_evidence"]
    pending = [
        p.name for p in (Path(journal) / "observations").glob("*.json")
        if not (Path(journal) / "settlements" / p.name).is_file()
    ]
    n = stats["nonpush_outcomes"]
    accuracy = {
        "status": "EVIDENCE_INVALID" if invalid or archives.get("invalid_captures") else
                  "INSUFFICIENT_OUTCOMES" if n < 100 else
                  "PROSPECTIVE_RESULTS_AVAILABLE_BROKER_PARITY_UNVERIFIED",
        "nonpush": n, "target": 100,
        "settled_win": stats["wins"], "settled_loss": stats["losses"],
        "settled_push": stats["pushes"], "abstained": score["counts"]["ABSTAINED"],
        "pending_observation_count": len(pending),
        "unsettled_observation_names": sorted(pending),
        "observed_win_rate": stats["observed_nonpush_win_rate"],
        "predictive_accuracy_certified": False,
        "invalid_evidence_count": len(invalid),
    }
    profitability = {
        "status": stats["status"],
        "statistical_edge_proven": False,
        "screen_passed": stats["statistical_screen_passed"],
        "payout_assumed": 0.80,
        "break_even_win_rate": stats["break_even_nonpush_win_rate_at_payout"],
        "wilson_95pct_interval": stats["wilson_95pct_nonpush_win_rate"],
        "one_sided_exact_p": stats["one_sided_exact_pvalue_vs_break_even"],
        "idealized_net_units": stats["idealized_net_units"],
        "limitations": stats["limitations"],
    }
    monitoring = local_monitor(
        health_url=local_health_url, duration_seconds=monitor_seconds
    ) if local_health_url is not None else local_monitor()
    deployment = production_check(health_url=production_health_url)
    return {
        "schema": 1, "generated_utc": utc_stamp(),
        "regular_eurusd_1min_15min_research_only": True,
        "archive_pass": {"captures": archives.get("captures_found"),
                         "new_settlements": len(archives.get("new_settlements", [])),
                         "invalid_captures": len(archives.get("invalid_captures", []))},
        "prediction_accuracy": accuracy,
        "profitability_statistics": profitability,
        "long_session_monitoring": monitoring,
        "production_deployment": deployment,
        "data_provider_http_requests": 0, "broker_orders": 0,
        "live_signal": "NO TRADE",
    }


def save_report(report, output=REPORTS):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    p = output / ("four_evidence_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output, prefix=".four_", delete=False) as f:
            tmp = Path(f.name)
            json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, p)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    return p


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--journal", type=Path, default=JOURNAL)
    p.add_argument("--out-dir", type=Path, default=REPORTS)
    p.add_argument("--local-health-url")
    p.add_argument("--monitor-seconds", type=int, default=0)
    p.add_argument("--production-health-url")
    p.add_argument("--preview-only", action="store_true", help="No archived settlement writes")
    args = p.parse_args(argv)
    if args.monitor_seconds and args.local_health_url is None:
        p.error("--monitor-seconds requires --local-health-url")
    report = run(
        journal=args.journal, settle_archives=not args.preview_only,
        local_health_url=args.local_health_url,
        monitor_seconds=args.monitor_seconds,
        production_health_url=args.production_health_url,
    )
    out = save_report(report, args.out_dir)
    print("ACCURACY:", report["prediction_accuracy"]["status"])
    print("DIRECTIONAL_OUTCOMES:", report["prediction_accuracy"]["nonpush"], "/ 100")
    print("PROFITABILITY:", report["profitability_statistics"]["status"])
    print("LONG_SESSION:", report["long_session_monitoring"]["status"])
    print("PRODUCTION:", report["production_deployment"]["status"])
    print("REPORT:", out)
    print("NO PROVIDER REQUESTS; NO BROKER ORDERS; NO ACCURACY OR PROFIT CLAIM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
