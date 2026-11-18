"""Offline Twelve Data usage planner. No HTTP requests."""

from dataclasses import dataclass
from math import ceil

DAILY_LIMIT = 800
MINUTE_LIMIT = 8
ALLOWED_INTERVALS = (1, 2, 3, 5, 15)


@dataclass(frozen=True)
class BudgetPlan:
    interval_minutes: int
    symbols: int
    hours_per_day: int
    credits_per_request: int
    estimated_daily_credits: int
    remaining_daily_credits: int
    within_daily_limit: bool
    within_minute_limit: bool


def calculate_plan(
    interval_minutes=3,
    symbols=1,
    hours_per_day=24,
    credits_per_request=1,
):
    if type(interval_minutes) is not int or (
        interval_minutes not in ALLOWED_INTERVALS
    ):
        raise ValueError("Unsupported polling interval")

    for value in (
        symbols, hours_per_day, credits_per_request
    ):
        if type(value) is not int or value < 1:
            raise ValueError("Positive integer required")

    if hours_per_day > 24:
        raise ValueError("Hours per day cannot exceed 24")

    requests_per_symbol = ceil(
        hours_per_day * 60 / interval_minutes
    )

    daily_cost = (
        requests_per_symbol
        * symbols
        * credits_per_request
    )

    minute_cost = symbols * credits_per_request

    return BudgetPlan(
        interval_minutes=interval_minutes,
        symbols=symbols,
        hours_per_day=hours_per_day,
        credits_per_request=credits_per_request,
        estimated_daily_credits=daily_cost,
        remaining_daily_credits=max(0, DAILY_LIMIT - daily_cost),
        within_daily_limit=daily_cost <= DAILY_LIMIT,
        within_minute_limit=minute_cost <= MINUTE_LIMIT,
    )


def main():
    print("=== TWELVE DATA OFFLINE CREDIT PLANNER ===")
    print("Assumption: 1 credit/request/symbol")
    print("No real API usage is checked.\n")

    for interval in ALLOWED_INTERVALS:
        plan = calculate_plan(interval_minutes=interval)

        print(
            f"Every {interval:2} min | "
            f"Daily: {plan.estimated_daily_credits:4} | "
            f"Remaining: {plan.remaining_daily_credits:3} | "
            f"Fits: {plan.within_daily_limit}"
        )

    print("\nNo HTTP requests made.")
    print("No authorization state changed.")


if __name__ == "__main__":
    main()
