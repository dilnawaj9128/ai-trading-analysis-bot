
import copy

import pandas as pd
import pytest

from dashboard.chart_data import (
    accepted_datasets,
    calculate_indicators,
    filter_time_window,
    load_chart_candles,
    session_comparison,
)
from dashboard.report_loader import DashboardReportError
from simulator.advanced_research import build_advanced_research
from tests.test_dataset_quality import make_dataset
from tests.test_session_research_overlap import shifted_dataset


def test_accepted_datasets_only(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    report = build_advanced_research([
        csv_path.parent,
        csv_path.parent,
    ])

    selected = accepted_datasets(report)

    assert len(selected) == 1
    assert report["datasets_duplicate"] == 1


def test_load_valid_candles(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    frame = load_chart_candles(csv_path.parent)

    assert len(frame) == 120
    assert frame["timestamp"].is_monotonic_increasing
    assert str(frame["timestamp"].dt.tz) == "UTC"


def test_indicators_have_warmup():
    frame = pd.DataFrame({
        "Close": [1.1 + i * 0.0001 for i in range(30)]
    })

    result = calculate_indicators(frame)

    assert result["EMA_9"].iloc[:8].isna().all()
    assert result["EMA_21"].iloc[:20].isna().all()
    assert result["RSI_14"].iloc[:14].isna().all()

    assert result["EMA_9"].iloc[8:].notna().all()
    assert result["EMA_21"].iloc[20:].notna().all()
    assert result["RSI_14"].iloc[14:].notna().all()


def test_rsi_rising_and_flat():
    rising = calculate_indicators(
        pd.DataFrame({
            "Close": [1.0 + i * 0.01 for i in range(30)]
        })
    )

    flat = calculate_indicators(
        pd.DataFrame({
            "Close": [1.0] * 30
        })
    )

    assert rising["RSI_14"].iloc[-1] == 100.0
    assert flat["RSI_14"].iloc[-1] == 50.0


def test_time_filter_is_inclusive():
    frame = pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-11-12T10:00:00Z",
            periods=10,
            freq="min",
        ),
        "Close": range(10),
    })

    selected = filter_time_window(
        frame,
        "2026-11-12T10:02:00Z",
        "2026-11-12T10:05:00Z",
    )

    assert len(selected) == 4
    assert selected["Close"].tolist() == [2, 3, 4, 5]


def test_time_filter_rejects_reverse_range():
    frame = pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-11-12T10:00:00Z",
            periods=3,
            freq="min",
        )
    })

    with pytest.raises(ValueError):
        filter_time_window(
            frame,
            "2026-11-12T10:02:00Z",
            "2026-11-12T10:00:00Z",
        )


def test_multi_session_comparison(tmp_path):
    first, _ = make_dataset(tmp_path / "first")

    second = shifted_dataset(
        tmp_path / "second",
        minutes=120,
    )

    report = build_advanced_research([
        first.parent,
        second,
    ])

    comparison = session_comparison(report)

    assert len(comparison) == 2
    assert comparison["Candles"].sum() == 240
    assert (comparison["Average range"] >= 0).all()


def test_reject_unaccepted_session_count(tmp_path):
    csv_path, _ = make_dataset(tmp_path)

    report = build_advanced_research([
        csv_path.parent
    ])

    tampered = copy.deepcopy(report)
    tampered["datasets_accepted"] = 2

    with pytest.raises(DashboardReportError):
        accepted_datasets(tampered)

