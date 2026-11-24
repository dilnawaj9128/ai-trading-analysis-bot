from datetime import datetime,timezone,timedelta
import pytest
from dashboard.real_data_monitor import manual_request_cooldown, allow_attempt

NOW=datetime(2026,11,21,10,30,tzinfo=timezone.utc)

def test_first_manual_allowed():
    assert manual_request_cooldown(None,now=NOW)['allowed']

def test_cooldown_blocks_under_minute():
    prior=(NOW-timedelta(seconds=15)).isoformat()
    assert manual_request_cooldown(prior,now=NOW)=={'allowed':False,'retry_after_seconds':45}

def test_manual_allowed_after_minute():
    prior=(NOW-timedelta(seconds=61)).isoformat()
    assert manual_request_cooldown(prior,now=NOW)['allowed']

def test_timezone_normalized():
    prior=(NOW-timedelta(seconds=70)).astimezone(timezone(timedelta(hours=5,minutes=30))).isoformat()
    assert manual_request_cooldown(prior,now=NOW)['allowed']

def test_bad_clock_or_cooldown_rejected():
    with pytest.raises(ValueError):manual_request_cooldown('2026-11-21T10:29:00',now=NOW)
    with pytest.raises(ValueError):manual_request_cooldown(None,now=NOW,seconds=1)
    with pytest.raises(ValueError):manual_request_cooldown((NOW+timedelta(seconds=1)).isoformat(),now=NOW)

def test_auto_cap_still_enforced():
    assert not allow_attempt(active=True,consent=True,attempts=3)
