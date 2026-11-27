import json
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import Thread
from urllib.request import urlopen

import pandas as pd
import pytest

from backend.nifty_dashboard import build_nifty_snapshot
from backend.stage49_server import ThreadingHTTPServer, make_dashboard_handler


NOW = datetime(2026, 11, 26, 6, 0, 30, tzinfo=timezone.utc)


@pytest.fixture
def monitor_data(tmp_path):
    last_open = NOW.replace(second=0) - timedelta(minutes=1)
    pd.DataFrame({
        "timestamp": pd.date_range(end=last_open, periods=70, freq="min"),
        "Open": 26000.0,
        "High": 26002.0,
        "Low": 25998.0,
        "Close": 26001.0,
    }).to_csv(tmp_path / "latest.csv", index=False)
    db_path = tmp_path / "predictions.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """CREATE TABLE predictions (
                timestamp TEXT, horizon INTEGER, expiry TEXT,
                direction TEXT, up_score REAL, result TEXT,
                PRIMARY KEY (timestamp, horizon)
            )"""
        )
        db.executemany(
            "INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    opened.isoformat(), horizon,
                    (opened + timedelta(minutes=horizon)).isoformat(),
                    direction, score, result,
                )
                for opened, horizon, direction, score, result in (
                    (last_open - timedelta(minutes=12), 5, "UP", 0.6, "WIN"),
                    (last_open - timedelta(minutes=2), 5, "DOWN", 0.4, "PENDING"),
                    (last_open, 10, "UP", 0.55, "PENDING"),
                )
            ],
        )
    return tmp_path


def snapshot(data_dir, now=NOW):
    return build_nifty_snapshot(data_dir, now=now)


def test_moves_from_live_to_stale_and_closed_without_discarding_chart(monitor_data):
    live = snapshot(monitor_data)
    assert live["state"] == "LIVE DATA"
    assert live["quality"]["age_seconds"] == 30
    assert len(live["candles"]) == 70
    assert len(live["candle_analysis"]) == len(live["candles"])
    assert "RSI_14" in live["candle_analysis"][-1]["indicators"]
    assert "EMA_20" in live["candle_analysis"][-2]["indicators"]
    assert live["signals"][10]["label"] == "UP"
    assert live["signals"][5]["label"] == "NO TRADE"
    assert live["signals"][15]["label"] == "NO TRADE"
    assert live["predictions"][5]["counts"]["WIN"] == 1

    stale = snapshot(monitor_data, NOW + timedelta(minutes=3))
    assert stale["state"] == "STALE DATA"
    assert stale["signals"][10]["label"] == "NO TRADE"
    assert stale["candles"] == live["candles"]

    closed = snapshot(monitor_data, NOW.replace(hour=10, minute=10))
    assert closed["state"] == "MARKET CLOSED"
    assert closed["signals"][10]["label"] == "NO TRADE"
    assert closed["quality"]["latest_completed_close_utc"] == "2026-11-26T06:00:00+00:00"


def test_incomplete_or_gapped_candles_cannot_activate_direction(monitor_data):
    path = monitor_data / "latest.csv"
    candles = pd.read_csv(path)
    candles.drop(index=1).to_csv(path, index=False)
    gapped = snapshot(monitor_data)
    assert gapped["state"] == "CANDLE GAPS"
    assert gapped["signals"][10]["label"] == "NO TRADE"

    candles.loc[len(candles)] = candles.iloc[-1].copy()
    candles.loc[len(candles) - 1, "timestamp"] = NOW.replace(second=0).isoformat()
    candles.to_csv(path, index=False)
    incomplete = snapshot(monitor_data)
    assert incomplete["state"] == "INVALID CANDLE DATA"
    assert incomplete["candles"] == []
    assert incomplete["signals"][10]["label"] == "NO TRADE"


def test_http_route_and_missing_data_do_not_create_a_database(tmp_path):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_dashboard_handler(tmp_path, tmp_path, nifty_dir=tmp_path),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/market-lens", timeout=5) as response:
            assert b"Completed candles" in response.read()
            assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
        with urlopen(base + "/static/market-lens/style.css", timeout=5) as response:
            assert b".chart-wrap" in response.read()
        with urlopen(base + "/static/market-lens/app.js", timeout=5) as response:
            assert b'const liveURL = "/api/nifty";' in response.read()
        with urlopen(base + "/api/nifty", timeout=5) as response:
            data = json.load(response)
        assert data["state"] == "WAITING FOR DATA"
        assert data["execution_enabled"] is False
        assert data["predictions"] is None
        assert not (tmp_path / "predictions.db").exists()
        assert all(s["label"] == "NO TRADE" for s in data["signals"].values())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_closed_session_refresh_uses_newer_upstox_candles(monkeypatch, monitor_data):
    from backend.nifty_upstox import UpstoxMinuteFeed

    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"status": "success", "data": {"candles": [
                ["2026-11-26T15:30:00+05:30", 10, 12, 9, 999, 0, 0],
                ["2026-11-26T15:29:00+05:30", 10, 12, 9, 11, 0, 0],
                ["2026-11-26T15:28:00+05:30", 10, 12, 9, 10, 0, 0],
            ]}}

    def get(url, **kwargs):
        calls.append(url)
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        assert not kwargs["allow_redirects"]
        return Response()

    monkeypatch.setattr("backend.nifty_upstox.requests.get", get)
    clock = NOW.replace(hour=17)
    feed = UpstoxMinuteFeed("test-token")
    result = build_nifty_snapshot(monitor_data, now=clock, upstox=feed)
    assert result["candle_source"] == "Direct Upstox candles"
    assert result["state"] == "MARKET CLOSED"
    assert result["quality"]["latest_completed_close_utc"] == "2026-11-26T10:00:00+00:00"
    assert [candle[4] for candle in result["candles"]] == [10, 11]
    assert not result["behind_session"]
    assert result["signals"][5]["label"] == "NO TRADE"
    build_nifty_snapshot(monitor_data, now=clock + timedelta(seconds=30), upstox=feed)
    assert len(calls) == 1


def test_upstox_error_preserves_snapshot_and_surfaces_feed_lag(monkeypatch, monitor_data):
    from types import SimpleNamespace

    from backend.nifty_upstox import UpstoxMinuteFeed

    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=401)

    monkeypatch.setattr("backend.nifty_upstox.requests.get", get)
    clock = NOW.replace(hour=17)
    feed = UpstoxMinuteFeed("test-token")
    result = build_nifty_snapshot(monitor_data, now=clock, upstox=feed)
    assert result["candle_source"] == "Monitor snapshot"
    assert result["behind_session"]
    assert result["refresh_note"] == "Upstox rejected the access token"
    assert result["quality"]["latest_completed_close_utc"] == "2026-11-26T06:00:00+00:00"
    build_nifty_snapshot(monitor_data, now=clock + timedelta(seconds=30), upstox=feed)
    assert len(calls) == 1
