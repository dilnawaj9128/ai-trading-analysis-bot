"""Session-limited monitored requests. Explicit opt-in; no background scheduler."""
from datetime import datetime,timezone,timedelta
MAX_ATTEMPTS=3
INTERVALS=(1,3,5)


def allow_attempt(*, active, consent, attempts, max_attempts=MAX_ATTEMPTS):
    return bool(active and consent and 0 <= attempts < max_attempts)


def fresh_observation_gate(last_request_time, interval_minutes, now=None):
    if interval_minutes not in INTERVALS:
        raise ValueError('Unsupported refresh interval')
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('UTC-aware clock required')
    if last_request_time is None: return True
    stamp=datetime.fromisoformat(last_request_time)
    if stamp.tzinfo is None: raise ValueError('Malformed prior request clock')
    return now.astimezone(timezone.utc) >= stamp.astimezone(timezone.utc)+timedelta(minutes=interval_minutes)
