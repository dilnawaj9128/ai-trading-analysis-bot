"""Offline tests: no real HTTP, no broker orders."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from market_data.research_capture import ResearchCaptureError, save_verified_research_frame


def fixture_result():
    start = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
    frame = pd.DataFrame([
        {"timestamp": start + timedelta(minutes=i),
         "Open": 1.1, "High": 1.101, "Low": 1.099, "Close": 1.1005}
        for i in range(120)
    ])
    return {
        "analysis_only": True, "execution_enabled": False,
        "symbol": "EUR/USD", "interval": "1min",
        "stale": False, "gaps": 0, "candles": 120,
        "latest_utc": frame["timestamp"].iloc[-1].isoformat(),
        "frame": frame,
    }


def test_capture_once_and_reuse_identical(tmp_path):
    source = fixture_result()
    prior = source["frame"].copy(deep=True)
    first = save_verified_research_frame(source, directory=tmp_path)
    again = save_verified_research_frame(source, directory=tmp_path)
    assert first["csv_saved"] == "SAVED"
    assert again["csv_saved"] == "ALREADY_EXISTS"
    assert first["csv_path"] == again["csv_path"]
    assert first["csv_sha256"] == again["csv_sha256"]
    assert first["extra_http_requests"] == 0
    assert first["broker_parity_verified"] is False
    assert source["frame"].equals(prior)
    assert len(pd.read_csv(first["csv_path"])) == 120


def test_gaps_rejected(tmp_path):
    source = fixture_result()
    source["frame"].loc[20, "timestamp"] += timedelta(seconds=10)
    with pytest.raises(ResearchCaptureError):
        save_verified_research_frame(source, directory=tmp_path)


def test_invalid_market_or_unverified_flag_rejected(tmp_path):
    source = fixture_result()
    source["execution_enabled"] = True
    with pytest.raises(ResearchCaptureError):
        save_verified_research_frame(source, directory=tmp_path)
    source["execution_enabled"] = False
    source["symbol"] = "EUR/USD OTC"
    with pytest.raises(ResearchCaptureError):
        save_verified_research_frame(source, directory=tmp_path)


def test_changed_latest_timestamp_rejected(tmp_path):
    source = fixture_result()
    source["latest_utc"] = "2026-11-20T00:00:00+00:00"
    with pytest.raises(ResearchCaptureError):
        save_verified_research_frame(source, directory=tmp_path)


def test_no_overwrite_of_corrupt_existing_capture(tmp_path):
    source = fixture_result()
    first = save_verified_research_frame(source, directory=tmp_path)
    from pathlib import Path
    Path(first["csv_path"]).write_text("corrupted")
    with pytest.raises(ResearchCaptureError):
        save_verified_research_frame(source, directory=tmp_path)
