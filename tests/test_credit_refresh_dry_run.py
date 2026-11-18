from market_data.credit_refresh_dry_run import (
    execute_refresh_dry_run,
)


def test_missing_approval_blocks(tmp_path):
    result = execute_refresh_dry_run(
        workspace=tmp_path,
        explicitly_approved=False,
    )

    assert result["status"] == "BLOCKED"
    assert not list(tmp_path.iterdir())


def test_successful_simulation(tmp_path):
    result = execute_refresh_dry_run(
        workspace=tmp_path,
        explicitly_approved=True,
    )

    assert result["status"] == "SIMULATED_SNAPSHOT_READY"
    assert result["credits_left"] == 7
    assert result["real_http_executed"] is False
    assert result["settlement_authorized"] is False


def test_failure_does_not_save_provider_snapshot(tmp_path):
    result = execute_refresh_dry_run(
        workspace=tmp_path,
        explicitly_approved=True,
        simulate_failure=True,
    )

    assert result["status"] == "UNCERTAIN"
    assert not (tmp_path / "dry_run_provider.json").exists()
    assert (tmp_path / "dry_run_budget.json").exists()
