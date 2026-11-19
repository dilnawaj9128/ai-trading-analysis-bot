"""Read-only Stage 27A preflight and immediate/queued session checks."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from dashboard.auto_refresh_policy import start_auto_refresh, finish_attempt
from dashboard.live_probe_readiness import (
    inspect_probe_readiness, due_for_live_refresh,
)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def save(tmp_path, *, status="VERIFIED", offset=0):
    path = tmp_path / "probe.json"
    path.write_text(json.dumps({"version": 1, "attempts": [{
        "id": "a" * 32,
        "status": status,
        "started_at": (NOW + timedelta(seconds=offset)).isoformat(),
    }]}))
    return path


def test_ready_after_cooldown(tmp_path):
    path = save(tmp_path, offset=-200)
    assert inspect_probe_readiness(path=path, now=NOW)["status"] == "READY"


def test_waiting_does_not_consume_attempt(tmp_path):
    path = save(tmp_path, offset=-97)
    decision = inspect_probe_readiness(path=path, now=NOW)
    assert decision["status"] == "WAITING_FOR_COOLDOWN"
    assert decision["seconds_left"] == 83
    session = start_auto_refresh(now=NOW, minutes=3, approved=True)
    session["status"] = "WAITING_FOR_COOLDOWN"
    session["next_due_at"] = (NOW + timedelta(seconds=83)).isoformat()
    assert session["attempts"] == 0
    assert not due_for_live_refresh(session, now=NOW + timedelta(seconds=83))
    assert inspect_probe_readiness(path=path, now=NOW + timedelta(seconds=83))["status"] == "READY"
    session["status"] = "ARMED"
    assert due_for_live_refresh(session, now=NOW + timedelta(seconds=83))


def test_unresolved_is_blocked(tmp_path):
    path = save(tmp_path, status="UNCERTAIN", offset=-500)
    assert inspect_probe_readiness(path=path, now=NOW)["status"] == "BLOCKED"
    assert inspect_probe_readiness(path=path, now=NOW)["seconds_left"] is None


def test_corrupt_and_future_history_blocked(tmp_path):
    path = tmp_path / "probe.json"
    path.write_text("not json")
    assert inspect_probe_readiness(path=path, now=NOW)["status"] == "BLOCKED"
    path = save(tmp_path, offset=60)
    assert inspect_probe_readiness(path=path, now=NOW)["status"] == "BLOCKED"


def test_missing_file_ready_without_creating_file(tmp_path):
    path = tmp_path / "probe.json"
    assert inspect_probe_readiness(path=path, now=NOW)["status"] == "READY"
    assert not path.exists()


def test_immediate_then_bounded_interval():
    state = start_auto_refresh(now=NOW, minutes=3, approved=True)
    state["next_due_at"] = NOW.isoformat()
    assert due_for_live_refresh(state, now=NOW)
    state = finish_attempt(state, now=NOW, successful=True)
    assert state["attempts"] == 1
    assert not due_for_live_refresh(state, now=NOW + timedelta(seconds=179))
    assert due_for_live_refresh(state, now=NOW + timedelta(seconds=180))
    for minute in (3, 6):
        state = finish_attempt(state, now=NOW + timedelta(minutes=minute), successful=True)
    assert state["attempts"] == 3
    assert not state["active"]
    assert not due_for_live_refresh(state, now=NOW + timedelta(minutes=9))


def test_page_code_wired_for_waiting_and_no_execution_bypass():
    page = Path(__file__).resolve().parents[1] / "dashboard/pages/9_Real_Data_Research.py"
    source = page.read_text()
    compile(source, str(page), "exec")
    assert "WAITING_FOR_COOLDOWN" in source
    assert "inspect_probe_readiness" in source
    assert "due_for_live_refresh" in source
    assert 'data_mode="unknown"' in source
    assert "execution_enabled=True" not in source
