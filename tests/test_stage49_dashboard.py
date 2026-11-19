import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.stage49_server import (
    FRONTEND,
    make_dashboard_handler,
    static_asset,
)


@contextmanager
def running_server(tmp_path):
    handler = make_dashboard_handler(
        tmp_path / "no-stage46-report",
        tmp_path / "no-stage47-report",
    )

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), handler
    )
    thread = threading.Thread(
        target=server.serve_forever, daemon=True
    )
    thread.start()

    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def fetch(base, path):
    with urlopen(base + path, timeout=5) as response:
        return (
            response.status,
            response.headers,
            response.read().decode("utf-8"),
        )


def test_frontend_files_exist():
    for file in ("index.html", "style.css", "app.js"):
        assert (FRONTEND / file).is_file()


def test_only_allowlisted_assets():
    assert static_asset("/") is not None
    assert static_asset("/static/app.js") is not None
    assert static_asset("/api/trade") is None
    assert static_asset("/static/../backend/stage48_api.py") is None


def test_dashboard_html_served(tmp_path):
    with running_server(tmp_path) as base:
        status, headers, body = fetch(base, "/")

    assert status == 200
    assert "text/html" in headers["Content-Type"]
    assert "MarketLens" in body
    assert "Content-Security-Policy" in headers


def test_dashboard_alias(tmp_path):
    with running_server(tmp_path) as base:
        status, _, body = fetch(base, "/dashboard")

    assert status == 200
    assert "Market Overview" in body


def test_css_and_js_served(tmp_path):
    with running_server(tmp_path) as base:
        css_status, _, css = fetch(base, "/static/style.css")
        js_status, _, js = fetch(base, "/static/app.js")

    assert css_status == 200
    assert js_status == 200
    assert ".sidebar" in css
    assert 'getJSON("/api/signal")' in js


def test_existing_api_available(tmp_path):
    with running_server(tmp_path) as base:
        status, _, body = fetch(base, "/api/signal")

    assert status == 200
    assert '"NO TRADE"' in body
    assert '"execution_enabled": false' in body


def test_missing_reports_fail_closed(tmp_path):
    with running_server(tmp_path) as base:
        status, _, body = fetch(base, "/api/research")

    assert status == 200
    assert "RESEARCH_EVIDENCE_INCOMPLETE" in body
    assert '"historical_metrics": null' in body


def test_write_requests_rejected(tmp_path):
    with running_server(tmp_path) as base:
        request = Request(
            base + "/api/signal",
            data=b"{}",
            method="POST",
        )
        try:
            urlopen(request, timeout=5)
            assert False, "POST unexpectedly succeeded"
        except HTTPError as error:
            assert error.code == 405
            assert b"READ_ONLY_API" in error.read()


def test_unknown_static_path_rejected(tmp_path):
    with running_server(tmp_path) as base:
        try:
            fetch(base, "/static/unknown.js")
            assert False, "Unknown asset unexpectedly served"
        except HTTPError as error:
            assert error.code == 404
