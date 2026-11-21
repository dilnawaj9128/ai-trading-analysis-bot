"""Regression: no duplicated credit-spending request inside active 15m window."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from research.real_prediction_campaign import (
    _envelope, preflight_observation_window,
)


def write_obs(folder, dt):
    d = folder / "observations"
    d.mkdir(parents=True, exist_ok=True)
    record = {
        "decision_time_utc": dt.isoformat(),
        "recorded_at_utc": (dt + timedelta(seconds=12)).isoformat(),
        "expiry_time_utc": (dt + timedelta(minutes=15)).isoformat(),
    }
    (d / "sample.json").write_text(json.dumps(_envelope("OBSERVATION", record)))


def test_no_prior_allowed(tmp_path):
    assert preflight_observation_window(tmp_path)["eligible"]


def test_recent_observation_blocks(tmp_path):
    now = datetime(2026, 11, 20, 15, 40, tzinfo=timezone.utc)
    write_obs(tmp_path, now-timedelta(minutes=2))
    result = preflight_observation_window(tmp_path, now=now)
    assert not result["eligible"]
    assert result["reason"] == "15_MINUTE_NONOVERLAP_WINDOW"


def test_after_window_allowed(tmp_path):
    now = datetime(2026, 11, 20, 15, 55, tzinfo=timezone.utc)
    write_obs(tmp_path, now-timedelta(minutes=17))
    assert preflight_observation_window(tmp_path, now=now)["eligible"]


def test_corrupt_record_fails_closed(tmp_path):
    now = datetime(2026, 11, 20, 15, 40, tzinfo=timezone.utc)
    write_obs(tmp_path, now-timedelta(minutes=2))
    path = tmp_path/"observations"/"sample.json"
    doc = json.loads(path.read_text())
    doc["record"]["expiry_time_utc"] = now.isoformat()
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="checksum"):
        preflight_observation_window(tmp_path, now=now)
