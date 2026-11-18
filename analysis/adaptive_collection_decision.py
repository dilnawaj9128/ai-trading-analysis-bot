"""Research-only historical collection decision engine."""

from dataclasses import dataclass
from math import ceil

from analysis.adaptive_training_controller import create_training_plan
from analysis.data_coverage import CoverageReport


@dataclass(frozen=True)
class CollectionDecision:
    target_days: int
    additional_days: int
    estimated_requests: int
    requests_this_run: int
    action: str
    reason: str


def decide_collection(
    coverage: CoverageReport,
    *,
    available_days: int,
    batch_candles: int = 400,
    max_requests: int = 5,
) -> CollectionDecision:

    if type(batch_candles) is not int or not 2 <= batch_candles <= 4999:
        raise ValueError("Invalid batch_candles")

    if type(max_requests) is not int or max_requests < 1:
        raise ValueError("Invalid max_requests")

    if not isinstance(coverage, CoverageReport):
        raise ValueError("CoverageReport required")

    plan = create_training_plan(available_days)

    # Approximation: 5 trading days per 7 calendar days.
    estimated_candles = ceil(
        plan.additional_days * (5 / 7) * 1440
    )

    estimated_requests = ceil(
        estimated_candles / batch_candles
    )

    requests_this_run = min(
        estimated_requests,
        max_requests,
    )

    if coverage.missing_candles > 0:
        action = "REPAIR_GAPS"
        reason = "Historical dataset contains missing market-open candles"

    elif plan.additional_days > 0:
        action = "COLLECT_MORE"
        reason = "Additional historical training data recommended"

    else:
        action = "EVALUATE_MODEL"
        reason = "Maximum configured training history reached"

    return CollectionDecision(
        target_days=plan.target_days,
        additional_days=plan.additional_days,
        estimated_requests=estimated_requests,
        requests_this_run=requests_this_run,
        action=action,
        reason=reason,
    )
