from datetime import datetime, timedelta, timezone

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.credit_dashboard_status import (
    get_credit_dashboard_status,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def save_snapshot(path, credits):
    save_credit_state(
        CreditSnapshot(
            credits_used=1,
            credits_left=credits,
            low_credits=credits < 20,
            information_available=True,
        ),
        path=path,
        now=NOW,
    )


def test_ready_credits(tmp_path):
    path = tmp_path / "credits.json"
    save_snapshot(path, 100)

    result = get_credit_dashboard_status(path=path, now=NOW)

    assert result["status"] == "READY"
    assert result["request_allowed"] is True
    assert result["credits_left"] == 100


def test_low_credits(tmp_path):
    path = tmp_path / "credits.json"
    save_snapshot(path, 1)

    result = get_credit_dashboard_status(path=path, now=NOW)

    assert result["status"] == "LOW_CREDITS"
    assert result["request_allowed"] is False


def test_missing_snapshot(tmp_path):
    result = get_credit_dashboard_status(
        path=tmp_path / "missing.json",
        now=NOW,
    )

    assert result["status"] == "UNKNOWN"
    assert result["request_allowed"] is False


def test_expired_snapshot(tmp_path):
    path = tmp_path / "credits.json"
    save_snapshot(path, 100)

    result = get_credit_dashboard_status(
        path=path,
        now=NOW + timedelta(minutes=6),
    )

    assert result["status"] == "UNKNOWN"
    assert result["request_allowed"] is False


def test_threshold_boundary(tmp_path):
    path = tmp_path / "credits.json"
    save_snapshot(path, 2)

    result = get_credit_dashboard_status(path=path, now=NOW)

    assert result["status"] == "READY"
    assert result["request_allowed"] is True
