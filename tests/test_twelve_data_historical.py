
from datetime import datetime, timedelta, timezone
import json

import pandas as pd
import pytest

from data.twelve_data_historical import download_eurusd
from data.historical_sessions import split_sessions


START = datetime(
    2026, 11, 12, 10, 0,
    tzinfo=timezone.utc,
)


def fake_response(params, key, count=90):
    assert params["symbol"] == "EUR/USD"
    assert params["interval"] == "1min"
    assert params["timezone"] == "UTC"
    assert key == "TEST_KEY"

    return {
        "status": "ok",
        "meta": {
            "symbol": "EUR/USD",
            "interval": "1min",
        },
        "values": [
            {
                "datetime": (
                    START + timedelta(minutes=i)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "open": str(1.10 + i * 0.00001),
                "high": str(1.11 + i * 0.00001),
                "low": str(1.09 + i * 0.00001),
                "close": str(1.105 + i * 0.00001),
            }
            for i in range(count)
        ],
    }


def run_download(tmp_path, fetcher):
    return download_eurusd(
        start=START,
        end=START + timedelta(minutes=90),
        retrieved_at=START + timedelta(minutes=100),
        output_dir=tmp_path / "download",
        api_key="TEST_KEY",
        fetcher=fetcher,
    )


def test_download_saves_utc_csv_and_receipt(tmp_path):
    csv_path, receipt_path = run_download(
        tmp_path, fake_response
    )

    frame = pd.read_csv(csv_path)
    receipt = json.loads(
        receipt_path.read_text(encoding="utf-8")
    )

    assert len(frame) == 90
    assert receipt["candle_count"] == 90
    assert receipt["feed_mode"] == "unknown"
    assert receipt["broker_verified"] is False
    assert receipt["provider_feed_mode_verified"] is False


def test_api_error_rejected(tmp_path):
    def error_response(params, key):
        return {
            "status": "error",
            "message": "Invalid API key",
        }

    with pytest.raises(ValueError, match="API"):
        run_download(tmp_path, error_response)


def test_duplicate_candle_rejected(tmp_path):
    def duplicate_response(params, key):
        payload = fake_response(params, key)
        payload["values"][5]["datetime"] = (
            payload["values"][4]["datetime"]
        )
        return payload

    with pytest.raises(ValueError, match="Duplicate"):
        run_download(tmp_path, duplicate_response)


def test_incomplete_candle_excluded(tmp_path):
    csv_path, _ = download_eurusd(
        start=START,
        end=START + timedelta(minutes=90),
        retrieved_at=START + timedelta(minutes=89, seconds=30),
        output_dir=tmp_path / "partial",
        api_key="TEST_KEY",
        fetcher=fake_response,
    )

    frame = pd.read_csv(csv_path)
    assert len(frame) == 89


def test_session_gap_splits_dataset():
    timestamps = [
        START + timedelta(minutes=i)
        for i in range(70)
    ] + [
        START + timedelta(minutes=i)
        for i in range(75, 145)
    ]

    frame = pd.DataFrame([
        {
            "timestamp": time,
            "Open": 1.10,
            "High": 1.11,
            "Low": 1.09,
            "Close": 1.105,
        }
        for time in timestamps
    ])

    sessions, summaries = split_sessions(frame)

    assert len(sessions) == 2
    assert [s.candle_count for s in summaries] == [70, 70]
    assert all(
        s.eligible_for_comparison
        for s in summaries
    )


def test_short_session_not_eligible():
    frame = pd.DataFrame([
        {
            "timestamp": START + timedelta(minutes=i),
            "Open": 1.10,
            "High": 1.11,
            "Low": 1.09,
            "Close": 1.105,
        }
        for i in range(40)
    ])

    _, summaries = split_sessions(frame)

    assert len(summaries) == 1
    assert summaries[0].eligible_for_comparison is False
def test_exact_end_boundary_is_excluded(tmp_path):
    def boundary_response(params, key):
        return fake_response(params, key, count=91)

    csv_path, receipt_path = download_eurusd(
        start=START,
        end=START + timedelta(minutes=90),
        retrieved_at=START + timedelta(minutes=100),
        output_dir=tmp_path / "boundary",
        api_key="TEST_KEY",
        fetcher=boundary_response,
    )

    frame = pd.read_csv(csv_path)

    assert len(frame) == 90

    receipt = json.loads(
        receipt_path.read_text(encoding="utf-8")
    )

    assert receipt["candle_count"] == 90
