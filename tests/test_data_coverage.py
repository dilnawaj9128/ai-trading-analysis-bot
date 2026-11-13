import pandas as pd
import pytest

from analysis.data_coverage import analyze_coverage


START = pd.Timestamp("2026-11-12T10:00:00Z")
END = pd.Timestamp("2026-11-12T10:10:00Z")


def make_frame(count=10):
    return pd.DataFrame({
        "timestamp": pd.date_range(
            START,
            periods=count,
            freq="min",
        )
    })


def test_complete_coverage():
    report = analyze_coverage(
        make_frame(),
        start=START,
        end=END,
    )

    assert report.actual_candles == 10
    assert report.expected_candles == 10
    assert report.missing_candles == 0
    assert report.coverage_percent == 100.0
    assert report.complete is True


def test_missing_candles():
    frame = make_frame().drop(index=[2, 5])

    report = analyze_coverage(
        frame,
        start=START,
        end=END,
    )

    assert report.actual_candles == 8
    assert report.missing_candles == 2
    assert report.coverage_percent == 80.0
    assert report.complete is False


def test_duplicate_timestamp_rejected():
    frame = make_frame()
    frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"]

    with pytest.raises(ValueError, match="Duplicate"):
        analyze_coverage(frame, start=START, end=END)


def test_outside_window_rejected():
    frame = make_frame()
    frame.loc[2, "timestamp"] = pd.Timestamp(
        "2026-11-13T10:00:00Z"
    )

    with pytest.raises(ValueError, match="outside"):
        analyze_coverage(frame, start=START, end=END)


def test_weekend_has_zero_expected_candles():
    report = analyze_coverage(
        pd.DataFrame({"timestamp": []}),
        start=pd.Timestamp("2026-11-14T10:00:00Z"),
        end=pd.Timestamp("2026-11-14T11:00:00Z"),
    )

    assert report.expected_candles == 0
    assert report.complete is True
