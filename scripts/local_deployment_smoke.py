"""Ephemeral localhost smoke test of the existing read-only app/API.

Does NOT publish a service, alter firewalls, use real provider APIs,
read credentials, or represent this test as production deployment.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _read(url, *, method="GET"):
    try:
        with urlopen(Request(url, method=method), timeout=3) as response:
            return response.status, response.headers, response.read(2_000_000)
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read(2_000_000)


def backend_smoke():
    """Launch actual Stage49 handler on an OS-assigned loopback port, then stop."""
    from backend.stage49_server import make_dashboard_handler
    server = None
    thread = None
    checks = {}
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler())
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_address[1])
        for path in ("/", "/static/style.css", "/static/app.js"):
            status, headers, body = _read(base + path)
            checks[path] = (status == 200 and bool(body)
                            and "nosniff" == headers.get("X-Content-Type-Options"))
        status, _, body = _read(base + "/api/health")
        obj = json.loads(body)
        checks["/api/health"] = (status == 200
                               and obj.get("status") == "ONLINE"
                               and obj.get("trading_execution_enabled") is False)
        status, _, body = _read(base + "/api/signal")
        obj = json.loads(body)
        checks["/api/signal"] = (status == 200
                               and obj.get("signal") == "NO TRADE"
                               and obj.get("execution_enabled") is False)
        status, _, body = _read(base + "/api/signal", method="POST")
        obj = json.loads(body)
        checks["POST /api/signal blocked"] = (status == 405
                    and obj.get("execution_enabled") is False)
        return {
            "status": "LOCAL_BACKEND_SMOKE_PASSED" if all(checks.values()) else "LOCAL_BACKEND_SMOKE_FAILED",
            "checks": checks, "bind_address": "127.0.0.1",
            "remote_production_deployment_verified": False,
        }
    except (OSError, ValueError, TypeError, KeyError, URLError) as exc:
        return {"status": "LOCAL_BACKEND_SMOKE_FAILED",
                "error_type": type(exc).__name__,
                "checks": checks,
                "remote_production_deployment_verified": False}
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=4)


def _unused_loopback_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def streamlit_smoke(*, seconds=12):
    """Ephemeral Streamlit health check, not browser E2E or uptime certification."""
    if importlib.util.find_spec("streamlit") is None:
        return {"status": "STREAMLIT_NOT_INSTALLED",
                "remote_production_deployment_verified": False}
    if not Path("dashboard/app.py").is_file():
        return {"status": "STREAMLIT_ENTRYPOINT_MISSING",
                "remote_production_deployment_verified": False}
    proc = None
    try:
        port = _unused_loopback_port()
        command = [
            sys.executable, "-m", "streamlit", "run", "dashboard/app.py",
            "--server.headless=true", "--server.address=127.0.0.1",
            "--server.port=" + str(port),
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ]
        env = dict(os.environ)
        env.pop("TWELVE_DATA_API_KEY", None)
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=env,
        )
        url = "http://127.0.0.1:" + str(port) + "/_stcore/health"
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return {"status": "STREAMLIT_EXITED_BEFORE_READY",
                        "remote_production_deployment_verified": False}
            try:
                code, _, body = _read(url)
                if code == 200 and b"ok" in body.lower():
                    return {
                        "status": "LOCAL_STREAMLIT_HEALTH_PASSED",
                        "bind_address": "127.0.0.1",
                        "remote_production_deployment_verified": False,
                    }
            except (OSError, URLError):
                pass
            time.sleep(0.25)
        return {"status": "STREAMLIT_LOCAL_HEALTH_TIMEOUT",
                "remote_production_deployment_verified": False}
    except (OSError, ValueError, TypeError) as exc:
        return {"status": "STREAMLIT_SMOKE_FAILED",
                "error_type": type(exc).__name__,
                "remote_production_deployment_verified": False}
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=4)


def deployment_smoke():
    api = backend_smoke()
    ui = streamlit_smoke()
    return {
        "api": api, "streamlit": ui,
        "status": (
            "LOCAL_SMOKE_PASSED_PRODUCTION_NOT_VERIFIED"
            if api["status"] == "LOCAL_BACKEND_SMOKE_PASSED"
            and ui["status"] == "LOCAL_STREAMLIT_HEALTH_PASSED"
            else "LOCAL_SMOKE_INCOMPLETE"
        ),
        "actual_remote_deployment": False,
        "real_24hour_uptime_tested": False,
        "https_domain_and_security_review_completed": False,
        "provider_requests": 0,
        "broker_orders": 0,
    }


if __name__ == "__main__":
    print(json.dumps(deployment_smoke(), indent=2, sort_keys=True))
