import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = load("stage28c_gate", ROOT / "market_data" / "probe_cross_path_gate.py")
patch = load("stage28c_patch", ROOT / "scripts" / "apply_stage28c.py")


def history(tmp_path, status):
    p = tmp_path / "probe.json"
    p.write_text(json.dumps({"version": 1, "attempts": [{
        "started_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "status": status,
    }]}))
    return p


def test_uncertain_is_blocked(tmp_path):
    p = history(tmp_path, "UNCERTAIN")
    with pytest.raises(gate.CrossPathProbeBlocked, match="unresolved"):
        with gate.hold_probe_gate(p):
            pytest.fail("Must never enter fetch")
    assert json.loads(p.read_text())["attempts"][0]["status"] == "UNCERTAIN"


def test_request_attempted_is_blocked(tmp_path):
    p = history(tmp_path, "REQUEST_ATTEMPTED")
    with pytest.raises(gate.CrossPathProbeBlocked):
        with gate.hold_probe_gate(p):
            pytest.fail("Must never enter fetch")


def test_verified_can_enter_without_consuming_budget(tmp_path):
    p = history(tmp_path, "VERIFIED")
    with gate.hold_probe_gate(p) as state:
        assert state == "VERIFIED"


def test_missing_history_is_not_falsely_unresolved(tmp_path):
    with gate.hold_probe_gate(tmp_path / "missing.json") as state:
        assert state == "NO_PROBE_HISTORY"


def test_malformed_history_fail_closed(tmp_path):
    p = tmp_path / "probe.json"
    p.write_text("{oops")
    with pytest.raises(gate.CrossPathProbeBlocked, match="invalid"):
        with gate.hold_probe_gate(p):
            pytest.fail("Must never enter fetch")


def test_future_clock_fail_closed(tmp_path):
    p = tmp_path / "probe.json"
    p.write_text(json.dumps({"version": 1, "attempts": [{
        "started_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "status": "VERIFIED",
    }]}))
    with pytest.raises(gate.CrossPathProbeBlocked):
        with gate.hold_probe_gate(p):
            pytest.fail("Must never enter fetch")


def test_source_patch_idempotent_and_preserves_future():
    src = '''"""Doc."""\nfrom __future__ import annotations\n\ndef fetch_recent_candles(config):\n    return config\n'''
    out = patch.patched(src, "fetch_recent_candles")
    assert "@guard_production_fetch\ndef fetch_recent_candles" in out
    assert out.index("from __future__") < out.index("from market_data.probe_cross_path_gate")
    assert out == patch.patched(out, "fetch_recent_candles")


def test_decorator_prevents_function_execution_on_uncertain(tmp_path, monkeypatch):
    p = history(tmp_path, "UNCERTAIN")
    monkeypatch.setattr(gate, "PROBE_STATE", p)
    called = []
    @gate.guard_production_fetch
    def api_call():
        called.append(True)
    with pytest.raises(gate.CrossPathProbeBlocked):
        api_call()
    assert called == []
