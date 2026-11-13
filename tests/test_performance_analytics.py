
from datetime import datetime, timedelta, timezone

import pytest

from database.models import StoredTrade
from simulator.performance_analytics import (
    build_performance_reports,
    calculate_report,
    filter_trades,
)


UTC = timezone.utc
START = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def make_trade(
    trade_id,
    source,
    expiry,
    result,
    pnl,
    offset=0,
):
    entry = START + timedelta(minutes=offset)
    closed = result != "OPEN"

    return StoredTrade(
        trade_id=trade_id,
        direction="UP",
        entry_price=100.0,
        stake=50.0,
        payout_rate=0.80,
        expiry_minutes=expiry,
        entry_time=entry,
        status="CLOSED" if closed else "OPEN",
        exit_price=101.0 if closed else None,
        exit_time=(
            entry + timedelta(minutes=expiry)
            if closed else None
        ),
        result=result if closed else None,
        profit_loss=pnl,
        trade_source=source,
        price_source=(
            "MANUAL_INPUT"
            if source == "MANUAL_TEST"
            else "HISTORICAL_CANDLE"
        ),
        expiry_price_time=None,
    )


@pytest.fixture
def sample_trades():
    return [
        make_trade("1", "MANUAL_TEST", 5, "WIN", 40, 0),
        make_trade("2", "MANUAL_TEST", 1, "LOSS", -50, 10),
        make_trade(
            "3", "HISTORICAL_RESEARCH", 15, "WIN", 40, 20
        ),
        make_trade(
            "4", "HISTORICAL_RESEARCH", 5, "PUSH", 0, 40
        ),
        make_trade(
            "5", "HISTORICAL_RESEARCH", 1, "OPEN", 0, 60
        ),
    ]


def test_overall_performance(sample_trades):
    report = calculate_report(sample_trades)

    assert report["total_trades"] == 5
    assert report["closed_trades"] == 4
    assert report["open_trades"] == 1
    assert report["wins"] == 2
    assert report["losses"] == 1
    assert report["pushes"] == 1
    assert report["total_pnl"] == pytest.approx(30)
    assert report["win_rate"] == pytest.approx(200 / 3)


def test_separate_source_reports(sample_trades):
    reports = build_performance_reports(sample_trades)

    manual = reports["sources"]["MANUAL_TEST"]
    historical = reports["sources"]["HISTORICAL_RESEARCH"]

    assert manual["total_trades"] == 2
    assert manual["total_pnl"] == pytest.approx(-10)

    assert historical["total_trades"] == 3
    assert historical["closed_trades"] == 2
    assert historical["open_trades"] == 1
    assert historical["total_pnl"] == pytest.approx(40)


def test_expiry_reports(sample_trades):
    reports = build_performance_reports(sample_trades)

    assert reports["expiry"][1]["total_trades"] == 2
    assert reports["expiry"][5]["total_trades"] == 2
    assert reports["expiry"][15]["total_trades"] == 1

    assert reports["expiry"][5]["total_pnl"] == pytest.approx(40)


def test_source_and_expiry_filter(sample_trades):
    filtered = filter_trades(
        sample_trades,
        source="HISTORICAL_RESEARCH",
        expiry_minutes=15,
    )

    assert len(filtered) == 1
    assert filtered[0].trade_id == "3"


def test_result_filter(sample_trades):
    filtered = filter_trades(
        sample_trades,
        result="OPEN",
    )

    assert len(filtered) == 1
    assert filtered[0].trade_id == "5"


def test_drawdown_and_profit_factor(sample_trades):
    report = calculate_report(sample_trades)

    # Realized P&L timeline: +40, -50, +40, 0.
    # Peak 40, trough -10 -> drawdown 50.
    assert report["maximum_drawdown"] == pytest.approx(50)
    assert report["gross_profit"] == pytest.approx(80)
    assert report["gross_loss"] == pytest.approx(50)
    assert report["profit_factor"] == pytest.approx(1.6)


def test_empty_report():
    report = calculate_report([])

    assert report["total_trades"] == 0
    assert report["total_pnl"] == 0
    assert report["win_rate"] == 0
    assert report["profit_factor"] is None
    assert report["maximum_drawdown"] == 0

