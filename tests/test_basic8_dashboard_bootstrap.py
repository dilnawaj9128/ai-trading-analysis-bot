from datetime import datetime, timedelta, timezone

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.credit_dashboard_status import get_credit_dashboard_status
from market_data.credit_bootstrap_policy import decide_credit_bootstrap

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def make_state(path, left):
    save_credit_state(
        CreditSnapshot(
            credits_used=1,
            credits_left=left,
            low_credits=left < 2,
            information_available=True,
        ),
        path=path,
        now=NOW,
    )


def test_basic8_dashboard_seven_credits_ready(tmp_path):
    path = tmp_path / "credits.json"
    make_state(path, 7)

    result = get_credit_dashboard_status(path=path, now=NOW)

    assert result["status"] == "READY"
    assert result["request_allowed"] is True


def test_basic8_bootstrap_normal_with_fresh_seven_credits(tmp_path):
    path = tmp_path / "credits.json"
    make_state(path, 7)

    result = decide_credit_bootstrap(path=path, now=NOW)

    assert result.action == "NORMAL"


def test_expired_provider_state_stays_blocked(tmp_path):
    path = tmp_path / "credits.json"
    make_state(path, 7)

    later = NOW + timedelta(minutes=6)

    dashboard = get_credit_dashboard_status(path=path, now=later)
    bootstrap = decide_credit_bootstrap(path=path, now=later)

    assert dashboard["status"] == "UNKNOWN"
    assert dashboard["request_allowed"] is False
    assert bootstrap.action == "REQUIRE_APPROVAL"
