"""Stage 48: local, read-only research dashboard API.

No provider calls. No broker integration. No directional signal
authorization. Binds to localhost by design.
"""

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGE46 = (
    PROJECT_ROOT
    / "data/research/stage46/walk_forward_reports"
)
DEFAULT_STAGE47 = PROJECT_ROOT / "data/research/stage47"

MAX_REPORT_BYTES = 1024 * 1024
ROUTES = frozenset({
    "/api/health",
    "/api/status",
    "/api/research",
    "/api/signal",
})


def read_latest_report(folder, stage):
    """Read most recently modified valid report.

    Corrupt or unexpected latest reports are not silently replaced
    by older reports. This avoids presenting stale evidence as new.
    """
    folder = Path(folder)

    if not folder.is_dir():
        return None, "REPORT_DIRECTORY_MISSING"

    files = list(folder.glob("*.json"))

    if not files:
        return None, "REPORT_NOT_FOUND"

    latest = max(files, key=lambda p: (p.stat().st_mtime_ns, p.name))

    try:
        if latest.is_symlink():
            return None, "REPORT_SYMLINK_NOT_ALLOWED"

        if latest.stat().st_size > MAX_REPORT_BYTES:
            return None, "REPORT_TOO_LARGE"

        with latest.open(encoding="utf-8") as handle:
            report = json.load(handle)

        if not isinstance(report, dict):
            return None, "REPORT_INVALID"

        if report.get("stage") != stage:
            return None, "REPORT_STAGE_MISMATCH"

        if (
            report.get("analysis_only") is not True
            or report.get("execution_enabled") is not False
            or report.get("api_requests_executed") != 0
        ):
            return None, "REPORT_SAFETY_FIELDS_INVALID"

        if (
            report.get("dataset_origin_verified") is not False
            or report.get("forward_accuracy_proven") is not False
        ):
            return None, "REPORT_PROVENANCE_CONFLICT"

        if not isinstance(report.get("dataset_sha256"), str):
            return None, "DATASET_HASH_MISSING"

        return report, None

    except (OSError, ValueError, TypeError, UnicodeError):
        return None, "REPORT_READ_ERROR"


def valid_metrics(metrics):
    if not isinstance(metrics, dict):
        return False

    fields = (
        "total_trades", "wins", "losses", "pushes",
        "resolved", "net_units", "win_rate_percent",
    )
    if not all(field in metrics for field in fields):
        return False

    try:
        import math

        total = metrics["total_trades"]
        wins = metrics["wins"]
        losses = metrics["losses"]
        pushes = metrics["pushes"]
        resolved = metrics["resolved"]
        net = metrics["net_units"]
        rate = metrics["win_rate_percent"]

        if any(
            type(value) is not int or value < 0
            for value in (total, wins, losses, pushes, resolved)
        ):
            return False

        if resolved != wins + losses:
            return False

        if total != resolved + pushes:
            return False

        if not isinstance(net, (int, float)) or not math.isfinite(net):
            return False

        if resolved:
            if not isinstance(rate, (int, float)):
                return False
            if not math.isfinite(rate):
                return False
            if abs(rate - 100 * wins / resolved) > 0.01:
                return False
        elif rate is not None:
            return False

        return True
    except (TypeError, ValueError, ZeroDivisionError):
        return False


def build_snapshot(stage46_dir=DEFAULT_STAGE46,
                   stage47_dir=DEFAULT_STAGE47):
    report46, error46 = read_latest_report(stage46_dir, 46)
    report47, error47 = read_latest_report(stage47_dir, 47)

    reconciliation_ok = (
        report46 is not None
        and report46.get("audit_type") == "STAGE36_WALK_FORWARD"
        and report46.get("status") == "OFFLINE_RECONCILED"
        and report46.get("errors") == []
        and valid_metrics(report46.get("metrics"))
    )

    checkpoints_ok = (
        report47 is not None
        and report47.get("status") == "CHECKPOINTS_PASSED"
        and type(report47.get("signal_checks")) is int
        and report47["signal_checks"] > 0
        and report47.get("signal_failures") == 0
        and type(report47.get("selection_checks")) is int
        and report47["selection_checks"] > 0
        and report47.get("selection_failures") == 0
    )

    hashes_match = (
        report46 is not None
        and report47 is not None
        and report46["dataset_sha256"] == report47["dataset_sha256"]
    )

    offline_evidence_ok = (
        reconciliation_ok and checkpoints_ok and hashes_match
    )

    return {
        "service": "STAGE48_LOCAL_RESEARCH_API",
        "market_feed": "NOT_CONNECTED",
        "feed_mode": "UNKNOWN",
        "dataset_origin_verified": False,
        "forward_accuracy_proven": False,
        "signal_authorized": False,
        "trading_execution_enabled": False,
        "api_requests_executed": 0,
        "research_status": (
            "OFFLINE_AUDITS_AVAILABLE"
            if offline_evidence_ok
            else "RESEARCH_EVIDENCE_INCOMPLETE"
        ),
        "reports": {
            "stage46": {
                "available": report46 is not None,
                "status": (
                    report46.get("status") if report46 else "UNAVAILABLE"
                ),
                "valid": bool(reconciliation_ok),
                "error": error46,
            },
            "stage47": {
                "available": report47 is not None,
                "status": (
                    report47.get("status") if report47 else "UNAVAILABLE"
                ),
                "valid": bool(checkpoints_ok),
                "error": error47,
            },
            "same_dataset": bool(hashes_match),
        },
        "historical_metrics": (
            report46["metrics"] if offline_evidence_ok else None
        ),
        "lookahead_checks": (
            {
                "signal_checks": report47["signal_checks"],
                "signal_failures": report47["signal_failures"],
                "selection_checks": report47["selection_checks"],
                "selection_failures": report47["selection_failures"],
            }
            if offline_evidence_ok else None
        ),
    }


def api_response(path, snapshot):
    """Pure API router. No side effects."""
    if path == "/api/health":
        return 200, {
            "service": snapshot["service"],
            "status": "ONLINE",
            "market_feed": "NOT_CONNECTED",
            "trading_execution_enabled": False,
        }

    if path == "/api/status":
        return 200, {
            key: snapshot[key]
            for key in (
                "market_feed", "feed_mode",
                "dataset_origin_verified",
                "forward_accuracy_proven",
                "signal_authorized",
                "trading_execution_enabled",
                "research_status",
                "reports",
            )
        }

    if path == "/api/research":
        return 200, {
            "research_status": snapshot["research_status"],
            "historical_metrics": snapshot["historical_metrics"],
            "lookahead_checks": snapshot["lookahead_checks"],
            "disclaimer": (
                "Offline exploratory research only. "
                "No verified live accuracy or profitability."
            ),
        }

    if path == "/api/signal":
        return 200, {
            "signal": "NO TRADE",
            "status": "BLOCKED",
            "reason_codes": [
                "DATA_PROVENANCE_UNVERIFIED",
                "FEED_MODE_UNKNOWN",
                "BROKER_PRICE_PARITY_UNVERIFIED",
                "INDEPENDENT_FORWARD_VALIDATION_PENDING",
            ],
            "expiry_minutes": 15,
            "directional_signal_authorized": False,
            "execution_enabled": False,
        }

    return 404, {"error": "NOT_FOUND"}


def make_handler(stage46_dir, stage47_dir):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, payload):
            body = json.dumps(
                payload, allow_nan=False
            ).encode("utf-8")

            self.send_response(status)
            self.send_header(
                "Content-Type", "application/json; charset=utf-8"
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parts = urlsplit(self.path)

            if parts.path not in ROUTES or parts.query:
                self.send_json(404, {"error": "NOT_FOUND"})
                return

            # Re-read reports on each request; no stale cache.
            snapshot = build_snapshot(stage46_dir, stage47_dir)
            status, payload = api_response(parts.path, snapshot)
            self.send_json(status, payload)

        def do_POST(self):
            self.send_json(405, {
                "error": "READ_ONLY_API",
                "execution_enabled": False,
            })

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--stage46-dir", type=Path, default=DEFAULT_STAGE46
    )
    parser.add_argument(
        "--stage47-dir", type=Path, default=DEFAULT_STAGE47
    )
    args = parser.parse_args()

    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged port: 1024-65535")

    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(args.stage46_dir, args.stage47_dir),
    )

    print(
        f"Stage 48 local API: http://127.0.0.1:{args.port}",
        flush=True,
    )
    print("Mode: READ_ONLY / NO TRADE / NO API FETCH", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
