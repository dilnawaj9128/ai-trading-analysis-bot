import pandas as pd

from analysis.checkpoint_collection_planner import (
    create_checkpoint_plan,
)


START = "2026-11-12T10:00:00Z"
END = "2026-11-12T10:20:00Z"


def make_plan(tmp_path):
    return create_checkpoint_plan(
        symbol="EUR/USD",
        start=START,
        end=END,
        output_dir=tmp_path,
        batch_candles=10,
        max_requests=5,
    )


def test_no_checkpoints(tmp_path):
    plan = make_plan(tmp_path)

    assert plan.total_batches == 2
    assert plan.cached_batches == 0
    assert plan.pending_batches == 2
    assert plan.requests_this_run == 2


def test_valid_checkpoint(tmp_path):
    plan = make_plan(tmp_path)
    plan.job_dir.mkdir(parents=True)

    timestamps = pd.date_range(
        "2026-11-12T10:00:00Z",
        periods=10,
        freq="min",
    )

    pd.DataFrame({
        "timestamp": timestamps,
        "Open": 1.10,
        "High": 1.12,
        "Low": 1.09,
        "Close": 1.11,
    }).to_csv(
        plan.job_dir / "batch_00000.csv",
        index=False,
    )

    updated = make_plan(tmp_path)

    assert updated.cached_batches == 1
    assert updated.pending_batches == 1
    assert updated.requests_this_run == 1


def test_invalid_checkpoint(tmp_path):
    plan = make_plan(tmp_path)
    plan.job_dir.mkdir(parents=True)

    pd.DataFrame({
        "timestamp": ["2026-11-12T10:00:00Z"],
        "Open": [1.10],
        "High": [0.50],
        "Low": [1.09],
        "Close": [1.11],
    }).to_csv(
        plan.job_dir / "batch_00000.csv",
        index=False,
    )

    updated = make_plan(tmp_path)

    assert updated.cached_batches == 0
    assert updated.invalid_checkpoints == 1
    assert updated.pending_batches == 2
