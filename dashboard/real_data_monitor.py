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


def manual_request_cooldown(last_attempt_utc, *, now=None, seconds=60):
    """Prevent accidental repeated paid requests within one minute. No HTTP."""
    if not isinstance(seconds, int) or seconds < 60:
        raise ValueError('Cooldown cannot be less than 60 seconds')
    if last_attempt_utc is None:
        return {'allowed': True, 'retry_after_seconds': 0}
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('UTC-aware clock required')
    stamp = datetime.fromisoformat(last_attempt_utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Prior request clock must be timezone-aware')
    elapsed = (now.astimezone(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()
    if elapsed < 0:
        raise ValueError('Clock moved backwards')
    remaining = max(0, int((seconds-elapsed)+0.999999))
    return {'allowed': remaining == 0, 'retry_after_seconds': remaining}
