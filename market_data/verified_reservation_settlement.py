"""Conservative request-bound reservation settlement; offline and fail-closed.

This module does NOT refund provider credits or update provider snapshots.
A verified provider response already includes that request in reported credits;
settlement removes only its *duplicate local pending reservation*. An uncertain,
legacy, or receipt-less reservation stays counted. No broker or HTTP integration.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from market_data.authorization_journal import journal_path_for, load_journal
from market_data.provider_credit_state import DEFAULT_PATH
from market_data.unified_request_guard import _load_ledger, _save_json_atomic


class VerifiedSettlementBlocked(RuntimeError):
    pass


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'),
                                   allow_nan=False).encode('utf-8')).hexdigest()


def _read(path):
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if type(obj) is not dict:
        raise VerifiedSettlementBlocked('Invalid evidence object')
    return obj


def _receipt_path(provider, rid):
    if type(rid) is not str or len(rid) != 32 or any(c not in '0123456789abcdef' for c in rid):
        raise VerifiedSettlementBlocked('Invalid request ID')
    return provider.parent / 'verified_settlement_receipts' / (rid + '.json')


def _write_once(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.receipt_', suffix='.tmp', delete=False) as f:
            tmp = Path(f.name)
            json.dump(payload, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)  # create only: never overwrite a receipt
        except FileExistsError:
            if _read(path) != payload:
                raise VerifiedSettlementBlocked('Conflicting historical settlement receipt')
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def valid_recovery_settlement_receipt(provider_path, rid, recovery):
    """Used by recovery gate after settlement; no mutation and no HTTP."""
    try:
        provider = Path(provider_path)
        receipt = _read(_receipt_path(provider, rid))
        return (receipt.get('version') == 1
                and receipt.get('request_id') == rid
                and receipt.get('source') == 'STAGE52D_RECOVERY'
                and receipt.get('evidence_sha256') == _digest(recovery)
                and receipt.get('credits') == 1)
    except (OSError, ValueError, TypeError, KeyError, VerifiedSettlementBlocked):
        return False


def _proof_for_historical(provider, rid, kind):
    if kind == 'STAGE52D_RECOVERY':
        record = _read(provider.parent / 'stage52d_new_recovery_probe.json')
        if (record.get('request_id') != rid or record.get('status') != 'VERIFIED'
            or record.get('checkpoint') != 'VERIFIED'
            or record.get('http_attempted') is not True
            or record.get('trading_enabled') is not False
            or type(record.get('credits_left')) is not int or record['credits_left'] < 0
            or type(record.get('candles')) is not int or record['candles'] < 1):
            raise VerifiedSettlementBlocked('Recovery does not have verified request-bound outcome')
        # Full original evidence chain, including CSV digest, immutable case,
        # original UNCERTAIN request, and current PENDING ledger.
        from market_data.recovery_verified_gate import verified_recovery_override
        if not verified_recovery_override(provider.parent / 'approved_research_probe.json'):
            raise VerifiedSettlementBlocked('Recovery integrity attestation failed')
        return _digest(record)
    if kind == 'VERIFIED_RENEWAL':
        log = _read(provider.parent / 'verified_credit_renewals.json')
        if log.get('version') != 1 or type(log.get('attempts')) is not list:
            raise VerifiedSettlementBlocked('Invalid renewal journal')
        matching = [a for a in log['attempts'] if type(a) is dict and a.get('request_id') == rid]
        if len(matching) != 1:
            raise VerifiedSettlementBlocked('Ambiguous renewal receipt')
        a = matching[0]
        if (a.get('status') != 'VERIFIED' or a.get('http_attempted') is not True
            or type(a.get('credits_left')) is not int or a['credits_left'] < 0
            or type(a.get('candles')) is not int or a['candles'] < 1
            or type(a.get('verified_at_utc')) is not str):
            raise VerifiedSettlementBlocked('Renewal has no verified request-bound response')
        verified_at = datetime.fromisoformat(a['verified_at_utc'])
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise VerifiedSettlementBlocked('Invalid renewal timestamp')
        return _digest(a)
    if kind == 'INDEPENDENT_USAGE_RECOVERY':
        log = _read(provider.parent / 'independent_usage_recovery.json')
        if log.get('version') != 1 or type(log.get('attempts')) is not list:
            raise VerifiedSettlementBlocked('Invalid independent usage journal')
        matches = [e for e in log['attempts'] if type(e) is dict and e.get('request_id') == rid]
        if len(matches) != 1:
            raise VerifiedSettlementBlocked('Ambiguous independent usage record')
        record = matches[0]
        if (record.get('status') != 'VERIFIED'
            or record.get('http_attempted') is not True
            or record.get('endpoint') != 'api_usage'
            or type(record.get('credits_left')) is not int
            or record['credits_left'] < 0
            or type(record.get('credits_used')) is not int
            or record['credits_used'] < 0
            or type(record.get('verified_at_utc')) is not str):
            raise VerifiedSettlementBlocked('No verified independent usage receipt')
        stamp = datetime.fromisoformat(record['verified_at_utc'])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise VerifiedSettlementBlocked('Naive independent usage timestamp')
        return _digest(record)
    raise VerifiedSettlementBlocked('Unsupported evidence source')


def _settle_locked(provider, rid, source, evidence_sha):
    ledger_path = provider.with_name(provider.name + '.reservations.json')
    if not ledger_path.exists():
        raise VerifiedSettlementBlocked('Reservation ledger missing')
    ledger = _load_ledger(ledger_path)
    journal = load_journal(journal_path_for(provider))
    tx = journal['transactions'].get(rid)
    entry = ledger['requests'].get(rid)
    if (type(tx) is not dict or tx.get('status') != 'FINALIZED'
        or type(entry) is not dict or tx.get('credits') != 1 or entry.get('credits') != 1):
        raise VerifiedSettlementBlocked('Missing matched final authorization')
    status = entry.get('status')
    if status not in ('PENDING', 'SETTLED'):
        raise VerifiedSettlementBlocked('Uncertain reservations cannot be settled')
    receipt = {'version': 1, 'request_id': rid, 'credits': 1,
               'source': source, 'evidence_sha256': evidence_sha}
    path = _receipt_path(provider, rid)
    if status == 'SETTLED':
        if not path.exists() or _read(path) != receipt:
            raise VerifiedSettlementBlocked('Settled ledger lacks matching receipt')
        return False
    if ledger['reserved'] < 1:
        raise VerifiedSettlementBlocked('Inconsistent aggregate reservation')
    _write_once(path, receipt)
    entry['status'] = 'SETTLED'
    ledger['reserved'] -= 1
    _save_json_atomic(ledger_path, ledger)
    return True


def _lock(provider):
    return provider.with_name(provider.name + '.lock')


def reconcile_verified_historical(*, provider_path=DEFAULT_PATH):
    """Settle only old successful Stage52D/renewal IDs. No request is retried."""
    provider = Path(provider_path)
    lock_path = _lock(provider)
    provider.parent.mkdir(parents=True, exist_ok=True)
    settled, already, held = [], [], []
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if (os.fstat(lock.fileno()).st_dev, os.fstat(lock.fileno()).st_ino) != (
                os.stat(lock_path).st_dev, os.stat(lock_path).st_ino):
                raise VerifiedSettlementBlocked('Provider lock identity changed')
            from market_data.recovery_authorization import check_recovery_accounting
            check_recovery_accounting(provider)
            ledger = _load_ledger(provider.with_name(provider.name + '.reservations.json'))
            # Determine candidate IDs only from actual local verified outcome journals.
            candidates = []
            recovery_path = provider.parent / 'stage52d_new_recovery_probe.json'
            if recovery_path.exists():
                recovery = _read(recovery_path)
                if recovery.get('status') == 'VERIFIED':
                    candidates.append((recovery.get('request_id'), 'STAGE52D_RECOVERY'))
            renewal_path = provider.parent / 'verified_credit_renewals.json'
            if renewal_path.exists():
                renewal = _read(renewal_path)
                if renewal.get('version') != 1 or type(renewal.get('attempts')) is not list:
                    raise VerifiedSettlementBlocked('Invalid renewal journal')
                for a in renewal['attempts']:
                    if type(a) is not dict:
                        raise VerifiedSettlementBlocked('Invalid renewal attempt')
                    if a.get('status') == 'VERIFIED':
                        candidates.append((a.get('request_id'), 'VERIFIED_RENEWAL'))
            independent_path = provider.parent / 'independent_usage_recovery.json'
            if independent_path.exists():
                independent = _read(independent_path)
                if independent.get('version') != 1 or type(independent.get('attempts')) is not list:
                    raise VerifiedSettlementBlocked('Invalid independent usage journal')
                for e in independent['attempts']:
                    if type(e) is not dict:
                        raise VerifiedSettlementBlocked('Invalid independent usage record')
                    if e.get('status') == 'VERIFIED':
                        candidates.append((e.get('request_id'), 'INDEPENDENT_USAGE_RECOVERY'))
            proven = []
            seen_ids = set()
            # Verify every eligible source BEFORE performing any settlement.
            # This avoids partially settling a batch due to a later bad record.
            for rid, kind in candidates:
                if type(rid) is not str or rid not in ledger['requests']:
                    held.append('unbound_verified_record')
                    continue
                if rid in seen_ids:
                    raise VerifiedSettlementBlocked('Duplicate verified request evidence')
                seen_ids.add(rid)
                entry = ledger['requests'][rid]
                if entry['status'] == 'SETTLED':
                    receipt = _read(_receipt_path(provider, rid))
                    if receipt.get('source') != kind or receipt.get('request_id') != rid:
                        raise VerifiedSettlementBlocked('Settled receipt identity mismatch')
                    if kind == 'STAGE52D_RECOVERY':
                        from market_data.recovery_verified_gate import verified_recovery_override
                        if not verified_recovery_override(provider.parent / 'approved_research_probe.json'):
                            raise VerifiedSettlementBlocked('Settled recovery attestation invalid')
                    already.append(rid[:10])
                    continue
                if entry['status'] != 'PENDING':
                    held.append(rid[:10])
                    continue
                proven.append((rid, kind, _proof_for_historical(provider, rid, kind)))
            for rid, kind, digest in proven:
                if _settle_locked(provider, rid, kind, digest):
                    settled.append(rid[:10])
            remaining = _load_ledger(provider.with_name(provider.name + '.reservations.json'))
            return {'status': 'RECONCILED', 'settled_request_prefixes': settled,
                    'already_settled_prefixes': already, 'held': held,
                    'outstanding_reserved': remaining['reserved'],
                    'legacy_reserved': remaining['legacy_reserved'],
                    'http_requests': 0, 'old_uncertain_unchanged': True}
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def settle_verified_normal(*, provider_path=DEFAULT_PATH, request_id,
                           credits_left, candles, observed_at=None):
    """For future successful fetches only; called after validated HTTP+headers.

    Does not settle any earlier ID. The caller supplies the request ID returned
    by its own authorization and verified response metadata, never a stale
    provider balance alone.
    """
    if type(credits_left) is not int or credits_left < 0 or type(candles) is not int or candles < 1:
        raise VerifiedSettlementBlocked('Missing authenticated success metadata')
    seen = observed_at or datetime.now(timezone.utc)
    if not isinstance(seen, datetime) or seen.tzinfo is None or seen.utcoffset() is None:
        raise VerifiedSettlementBlocked('Invalid observation time')
    provider = Path(provider_path)
    evidence = {'request_id': request_id, 'credits_left': credits_left,
                'candles': candles, 'observed_at': seen.astimezone(timezone.utc).isoformat()}
    lock_path = _lock(provider)
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            from market_data.recovery_authorization import check_recovery_accounting
            check_recovery_accounting(provider)
            return _settle_locked(provider, request_id, 'NORMAL_VERIFIED_HTTP', _digest(evidence))
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
