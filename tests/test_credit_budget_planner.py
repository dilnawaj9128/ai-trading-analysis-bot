import pytest

from analysis.credit_budget_planner import calculate_plan


def test_one_minute_exceeds_daily_limit():
    plan = calculate_plan(interval_minutes=1)
    assert plan.estimated_daily_credits == 1440
    assert not plan.within_daily_limit


def test_two_minutes_fits_daily_limit():
    plan = calculate_plan(interval_minutes=2)
    assert plan.estimated_daily_credits == 720
    assert plan.within_daily_limit


def test_three_minutes_fits_daily_limit():
    plan = calculate_plan(interval_minutes=3)
    assert plan.estimated_daily_credits == 480
    assert plan.remaining_daily_credits == 320


def test_multiple_symbols_increase_usage():
    plan = calculate_plan(interval_minutes=3, symbols=2)
    assert plan.estimated_daily_credits == 960
    assert not plan.within_daily_limit


def test_minute_limit_rejects_excess():
    plan = calculate_plan(
        interval_minutes=3,
        symbols=9,
    )
    assert not plan.within_minute_limit


def test_invalid_interval_rejected():
    with pytest.raises(ValueError):
        calculate_plan(interval_minutes=0)
