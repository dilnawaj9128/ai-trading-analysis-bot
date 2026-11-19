"""Stage 52D: durable probe checkpoint regression tests."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

from scripts import approved_real_data_probe as probe


NOW = datetime(2026, 11, 19, 12, 30, tzinfo=timezone.utc)


def options(tmp_path, session):
    return {
        "approved": True,
        "api_key": "OFFLINE_TEST_KEY",
        "state_path": tmp_path / "probe.json",
        "budget_path": tmp_path / "budget.json",
        "provider_path": tmp_path / "credits.json",
        "csv_path": tmp_path / "candles.csv",
        "now": NOW,
        "session": session,
    }


def last_attempt(kwargs):
    path = kwargs["state_path"]
    return json.loads(path.read_text())["attempts"][-1]


@pytest.fixture(autouse=True)
def fake_budget(monkeypatch):
    monkeypatch.setattr(
        probe.td,
        "reserve_request",
        lambda **kwargs: None,
    )


def test_timeout_retains_request_checkpoint(tmp_path):
    class TimeoutSession:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            raise requests.exceptions.ReadTimeout("simulated")

    session = TimeoutSession()
    kwargs = options(tmp_path, session)

    with pytest.raises(requests.exceptions.ReadTimeout):
        probe.probe_once(**kwargs)

    attempt = last_attempt(kwargs)

    assert attempt["status"] == "UNCERTAIN"
    assert attempt["checkpoint"] == "REQUEST_ATTEMPTED"
    assert attempt["failure_category"] == "READ_TIMEOUT"
    assert session.calls == 1

    with pytest.raises(probe.ProbeBlocked, match="unresolved"):
        probe.probe_once(**kwargs)

    assert session.calls == 1


def test_invalid_json_preserves_http_checkpoint(tmp_path):
    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("Simulated invalid JSON")

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    kwargs = options(tmp_path, Session())

    with pytest.raises(ValueError, match="Simulated invalid JSON"):
        probe.probe_once(**kwargs)

    attempt = last_attempt(kwargs)

    assert attempt["status"] == "UNCERTAIN"
    assert attempt["checkpoint"] == "HTTP_ACCEPTED"
    assert attempt["failure_category"] == "LOCAL_OR_RESPONSE_ERROR"
    assert "checkpoint_at_utc" in attempt


def test_success_records_final_checkpoint(tmp_path, monkeypatch):
    class Frame:
        def to_csv(self, path, index=False):
            from pathlib import Path
            Path(path).write_text(
                "timestamp,Open,High,Low,Close\n"
                "2026-11-19,1,2,1,2\n"
            )

    monkeypatch.setattr(
        probe.td,
        "parse_candles",
        lambda *args, **kwargs: {
            "frame": Frame(),
            "candles": 1,
            "latest_utc": NOW.isoformat(),
            "stale": False,
        },
    )
    monkeypatch.setattr(
        probe,
        "refresh_credits_from_response",
        lambda *args, **kwargs: SimpleNamespace(
            updated=True,
            credits_left=7,
        ),
    )

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"values": [1]}

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    kwargs = options(tmp_path, Session())
    result = probe.probe_once(**kwargs)

    attempt = last_attempt(kwargs)

    assert result["status"] == "VERIFIED"
    assert attempt["status"] == "VERIFIED"
    assert attempt["checkpoint"] == "VERIFIED"
    assert len(attempt["csv_sha256"]) == 64
    assert kwargs["csv_path"].exists()
