"""Offline, consent-bound monitoring safety primitives.

Never calls the provider or brokers. Streamlit page owns approval and I/O.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

MAX_AUTO_ATTEMPTS = 3
ALLOWED_CADENCES_MINUTES = (1, 3, 5)


def utc_clock(now=None):
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Timezone-aware clock required')
    return now.astimezone(timezone.utc)


def due_for_auto_fetch(*, running, consent, attempts, in_progress,
                       last_attempt_utc, cadence_minutes, now=None):
    """Read-only gate; never authorizes quota or a provider HTTP request."""
    clock = utc_clock(now)
    if cadence_minutes not in ALLOWED_CADENCES_MINUTES or type(cadence_minutes) is not int:
        raise ValueError('Unsupported cadence')
    if type(attempts) is not int or attempts < 0:
        raise ValueError('Invalid attempt counter')
    if not running or not consent or in_progress or attempts >= MAX_AUTO_ATTEMPTS:
        return False
    if last_attempt_utc is None:
        return True
    stamp = datetime.fromisoformat(last_attempt_utc)
    previous = utc_clock(stamp)
    if previous > clock:
        # A backwards clock change must not cause an early fetch.
        return False
    return clock >= previous + timedelta(minutes=cadence_minutes)


def begin_attempt(state, *, manual=False, now=None):
    """Mutate a Streamlit-session-like mapping atomically inside one callback.

    No network, no ledger mutation. Provider guard still decides authorization.
    """
    if state.get('rdm_fetch_in_progress', False):
        return False
    if not state.get('rdm_monitor_approval', False):
        return False
    if manual:
        # Manual cooldown is independently checked by the existing UI.
        state['rdm_manual_attempts'] = state.get('rdm_manual_attempts', 0) + 1
        state['rdm_last_manual_attempt'] = utc_clock(now).isoformat()
    else:
        if not state.get('rdm_running', False):
            return False
        count = state.get('rdm_attempts', 0)
        if type(count) is not int or count < 0 or count >= MAX_AUTO_ATTEMPTS:
            return False
        state['rdm_attempts'] = count + 1
        state['rdm_last_req'] = utc_clock(now).isoformat()
    state['rdm_fetch_in_progress'] = True
    return True


def end_attempt(state, *, success: bool):
    state['rdm_fetch_in_progress'] = False
    if not success or state.get('rdm_attempts', 0) >= MAX_AUTO_ATTEMPTS:
        state['rdm_running'] = False
