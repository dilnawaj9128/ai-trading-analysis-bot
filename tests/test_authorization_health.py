from analysis.authorization_health import get_authorization_health
from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from datetime import datetime, timezone


NOW = datetime.now(timezone.utc)


def test_missing_evidence_is_possible_first_run(tmp_path):
    report = get_authorization_health(tmp_path / "provider.json")

    assert report["evidence_status"] == "POSSIBLE_FIRST_RUN"
    assert report["live_fetch_authorized"] is False


def test_recovery_marker_blocks(tmp_path):
    provider = tmp_path / "provider.json"
    recovery = tmp_path / "provider.json.recovery_required.json"
    recovery.write_text("marker")

    report = get_authorization_health(provider)

    assert report["recovery_marker"] is True
    assert report["live_fetch_authorized"] is False


def test_fresh_snapshot_does_not_grant_authorization(tmp_path):
    provider = tmp_path / "provider.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=1,
            credits_left=7,
            low_credits=False,
            information_available=True,
        ),
        path=provider,
        now=NOW,
    )

    report = get_authorization_health(provider)

    assert report["provider_status"] == "READY"
    assert report["live_fetch_authorized"] is False
