"""Research-only adaptive historical data planning."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrainingPlan:
    available_days: int
    target_days: int
    additional_days: int
    ready_for_evaluation: bool
    reason: str


def create_training_plan(
    available_days: int,
    *,
    stages=(30, 60, 90, 180),
) -> TrainingPlan:
    if type(available_days) is not int or available_days < 0:
        raise ValueError("available_days must be a non-negative integer")

    if not stages or any(
        type(day) is not int or day <= 0 for day in stages
    ):
        raise ValueError("Invalid training stages")

    if tuple(sorted(set(stages))) != tuple(stages):
        raise ValueError("Training stages must be strictly increasing")

    target = next(
        (day for day in stages if available_days < day),
        stages[-1],
    )

    additional = max(0, target - available_days)

    return TrainingPlan(
        available_days=available_days,
        target_days=target,
        additional_days=additional,
        ready_for_evaluation=available_days >= stages[0],
        reason=(
            "Historical evaluation can begin; assess model stability"
            if available_days >= stages[0]
            else "Collect more data before initial evaluation"
        ),
    )
