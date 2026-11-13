import pytest

from analysis.adaptive_collection_decision import decide_collection
from analysis.data_coverage import CoverageReport


def make_coverage(missing=0):
    return CoverageReport(
        actual_candles=1000 - missing,
        expected_candles=1000,
        missing_candles=missing,
        coverage_percent=(1000 - missing) / 10,
        complete=missing == 0,
    )


def test_initial_collection():
    decision = decide_collection(
        make_coverage(),
        available_days=0,
    )

    assert decision.action == "COLLECT_MORE"
    assert decision.target_days == 30
    assert decision.requests_this_run == 5


def test_gap_repair_priority():
    decision = decide_collection(
        make_coverage(missing=10),
        available_days=30,
    )

    assert decision.action == "REPAIR_GAPS"


def test_maximum_history_reached():
    decision = decide_collection(
        make_coverage(),
        available_days=180,
    )

    assert decision.action == "EVALUATE_MODEL"
    assert decision.estimated_requests == 0
    assert decision.requests_this_run == 0


def test_request_limit_respected():
    decision = decide_collection(
        make_coverage(),
        available_days=7,
        max_requests=2,
    )

    assert decision.requests_this_run <= 2


@pytest.mark.parametrize(
    "batch,max_requests",
    [
        (0, 5),
        (5000, 5),
        (400, 0),
        (True, 5),
    ],
)
def test_invalid_limits(batch, max_requests):
    with pytest.raises(ValueError):
        decide_collection(
            make_coverage(),
            available_days=7,
            batch_candles=batch,
            max_requests=max_requests,
        )
