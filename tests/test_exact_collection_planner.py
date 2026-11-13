import pandas as pd
import pytest

from analysis.exact_collection_planner import (
    create_exact_collection_plan,
)


def test_weekday_collection():
    plan = create_exact_collection_plan(
        start="2026-11-12T10:00:00Z",
        end="2026-11-12T12:00:00Z",
        batch_candles=60,
        max_requests=1,
    )

    assert plan.expected_candles == 120
    assert plan.planned_requests == 2
    assert plan.requests_this_run == 1
    assert plan.remaining_requests == 1
    assert plan.analysis_only is True


def test_weekend_collection():
    plan = create_exact_collection_plan(
        start="2026-11-14T10:00:00Z",
        end="2026-11-14T12:00:00Z",
    )

    assert plan.expected_candles == 0
    assert plan.planned_requests == 0
    assert plan.requests_this_run == 0


def test_multi_session_collection():
    plan = create_exact_collection_plan(
        start="2026-11-13T21:00:00Z",
        end="2026-11-15T23:00:00Z",
        batch_candles=60,
    )

    assert plan.expected_candles == 120
    assert plan.planned_requests == 2


@pytest.mark.parametrize(
    "batch,max_requests",
    [
        (0, 5),
        (5000, 5),
        (400, 0),
        (True, 5),
    ],
)
def test_invalid_request_limits(batch, max_requests):
    with pytest.raises(ValueError):
        create_exact_collection_plan(
            start="2026-11-12T10:00:00Z",
            end="2026-11-12T12:00:00Z",
            batch_candles=batch,
            max_requests=max_requests,
        )


def test_misaligned_window_rejected():
    with pytest.raises(ValueError, match="align"):
        create_exact_collection_plan(
            start="2026-11-12T10:00:30Z",
            end="2026-11-12T12:00:00Z",
        )
