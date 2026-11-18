"""Credit-aware, offline-only historical collection planning."""

from analysis.exact_collection_planner import (
    create_exact_collection_plan,
)


def plan_credit_aware_collection(
    *,
    start,
    end,
    batch_candles=400,
    max_requests=5,
    available_credits=None,
    reserve_credits=20,
):
    if available_credits is not None and (
        type(available_credits) is not int
        or available_credits < 0
    ):
        raise ValueError("Invalid available credits")

    if type(reserve_credits) is not int or reserve_credits < 0:
        raise ValueError("Invalid credit reserve")

    plan = create_exact_collection_plan(
        start=start,
        end=end,
        interval="1min",
        batch_candles=batch_candles,
        max_requests=max_requests,
    )

    estimated_cost = plan.requests_this_run

    sufficient = (
        available_credits is not None
        and available_credits >= estimated_cost + reserve_credits
    )

    return {
        "expected_candles": plan.expected_candles,
        "planned_requests": plan.planned_requests,
        "requests_this_run": plan.requests_this_run,
        "remaining_requests": plan.remaining_requests,
        "estimated_minimum_credits": estimated_cost,
        "available_credits": available_credits,
        "reserve_credits": reserve_credits,
        "budget_sufficient": sufficient,
        "collection_authorized": False,
        "status": "DRY_RUN_ONLY",
        "analysis_only": True,
    }
