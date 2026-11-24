"""Conservative minute-scoped exposure while retaining every historical reservation.

Twelve Data Basic 8 grants a per-UTC-minute quota.  A pending request from an
older minute remains in the durable audit ledger, but cannot spend a credit in
a new minute. This helper never changes ledger state or provider observations.
"""
from datetime import datetime, timezone


def minute_pending_credits(ledger, *, now, observed_at):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Aware current time required')
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError('Aware credit observation required')
    minute = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    observation = observed_at.astimezone(timezone.utc)
    if observation > now.astimezone(timezone.utc):
        raise ValueError('Future credit observation')
    if type(ledger) is not dict or type(ledger.get('requests')) is not dict:
        raise ValueError('Invalid reservations')
    # Legacy aggregate reservations have no timestamp; cannot establish expiry.
    legacy = ledger.get('legacy_reserved')
    if type(legacy) is not int or legacy < 0:
        raise ValueError('Invalid legacy reservations')
    pending = legacy
    for entry in ledger['requests'].values():
        if type(entry) is not dict or entry.get('status') not in ('PENDING','UNCERTAIN','SETTLED'):
            raise ValueError('Invalid request entry')
        if entry['status'] == 'SETTLED':
            continue
        credits = entry.get('credits')
        if type(credits) is not int or credits < 1:
            raise ValueError('Invalid reserved credits')
        authorized = datetime.fromisoformat(entry['authorized_at'])
        if authorized.tzinfo is None or authorized.utcoffset() is None:
            raise ValueError('Unverifiable reservation timestamp')
        authorized = authorized.astimezone(timezone.utc)
        if authorized > now.astimezone(timezone.utc):
            raise ValueError('Future-dated reservation')
        # When the provider snapshot is from this minute, it already reports
        # consumption before its observation. Subtract only later reservations.
        if authorized >= minute and authorized >= observation:
            pending += credits
    return pending
