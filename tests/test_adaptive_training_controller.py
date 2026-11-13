import pytest

from analysis.adaptive_training_controller import create_training_plan


@pytest.mark.parametrize(
    "available,target,additional,ready",
    [
        (0, 30, 30, False),
        (7, 30, 23, False),
        (30, 60, 30, True),
        (60, 90, 30, True),
        (90, 180, 90, True),
        (180, 180, 0, True),
    ],
)
def test_adaptive_training_plan(
    available, target, additional, ready
):
    plan = create_training_plan(available)

    assert plan.target_days == target
    assert plan.additional_days == additional
    assert plan.ready_for_evaluation is ready


@pytest.mark.parametrize("days", [-1, 1.5, True, "30"])
def test_invalid_available_days(days):
    with pytest.raises(ValueError):
        create_training_plan(days)


def test_invalid_training_stages():
    with pytest.raises(ValueError):
        create_training_plan(
            30,
            stages=(30, 30, 90),
        )
