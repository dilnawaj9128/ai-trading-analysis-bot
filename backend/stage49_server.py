"""Stage 49: localhost-only dashboard and existing Stage 48 API."""

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from backend.stage48_api import (
    DEFAULT_STAGE46,
    DEFAULT_STAGE47,
    PROJECT_ROOT,
    make_handler,
)

FRONTEND = PROJECT_ROOT / "frontend"

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/dashboard": ("index.html", "text/html; charset=utf-8"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
    "/static/app.js": (
        "app.js", "application/javascript; charset=utf-8"
    ),
}


def static_asset(path):
    """Only exact allowlisted paths can access frontend files."""
    return ASSETS.get(path)


def make_dashboard_handler(stage46_dir=DEFAULT_STAGE46,
                           stage47_dir=DEFAULT_STAGE47):
    APIHandler = make_handler(stage46_dir, stage47_dir)

    class DashboardHandler(APIHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)

            asset = static_asset(parsed.path)

            if parsed.query and asset is None:
                self.send_json(404, {"error": "NOT_FOUND"})
                return

            if asset is None:
                super().do_GET()
                return

            filename, content_type = asset
            file = FRONTEND / filename

            try:
                body = file.read_bytes()
            except OSError:
                self.send_json(503, {
                    "error": "DASHBOARD_ASSET_UNAVAILABLE"
                })
                return

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "X-Content-Type-Options", "nosniff"
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "connect-src 'self'; "
                "img-src 'self'; "
                "base-uri 'none'; "
                "form-action 'none'; "
                "frame-ancestors 'none'"
            )
            self.send_header(
                "Content-Length", str(len(body))
            )
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--stage46-dir", type=Path, default=DEFAULT_STAGE46
    )
    parser.add_argument(
        "--stage47-dir", type=Path, default=DEFAULT_STAGE47
    )
    args = parser.parse_args()

    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535")

    handler = make_dashboard_handler(
        args.stage46_dir, args.stage47_dir
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), handler
    )

    print(
        f"Dashboard: http://127.0.0.1:{args.port}/",
        flush=True
    )
    print(
        "Stage 49: LOCAL / READ ONLY / NO TRADE",
        flush=True
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
