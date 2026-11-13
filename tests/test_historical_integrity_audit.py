import pandas as pd

from analysis.historical_integrity_audit import audit_forex_dataset


def candles(timestamps):
    return pd.DataFrame({
        "timestamp": timestamps,
        "Open": 1.10,
        "High": 1.12,
        "Low": 1.09,
        "Close": 1.11,
    })


def test_complete_weekday_dataset():
    start = pd.Timestamp("2026-11-12 10:00", tz="UTC")
    end = start + pd.Timedelta(minutes=5)

    frame = candles(pd.date_range(
        start, end, freq="min", inclusive="left"
    ))

    report = audit_forex_dataset(
        frame, start=start, end=end
    )

    assert report["complete"] is True
    assert report["missing_open_candles"] == 0


def test_missing_open_candle_detected():
    start = pd.Timestamp("2026-11-12 10:00", tz="UTC")
    end = start + pd.Timedelta(minutes=5)

    timestamps = pd.date_range(
        start, end, freq="min", inclusive="left"
    ).delete(2)

    report = audit_forex_dataset(
        candles(timestamps), start=start, end=end
    )

    assert report["complete"] is False
    assert report["missing_open_candles"] == 1


def test_sunday_closed_slots_excluded():
    start = pd.Timestamp("2026-11-15 21:30", tz="UTC")
    end = pd.Timestamp("2026-11-15 22:30", tz="UTC")

    timestamps = pd.date_range(
        "2026-11-15T22:00:00Z",
        end,
        freq="min",
        inclusive="left",
        tz="UTC",
    )

    report = audit_forex_dataset(
        candles(timestamps), start=start, end=end
    )

    assert report["expected_closed_slots"] == 30
    assert report["expected_open_candles"] == 30
    assert report["complete"] is True
