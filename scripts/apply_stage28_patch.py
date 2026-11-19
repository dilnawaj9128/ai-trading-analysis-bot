"""Stage 28: source-only, fail-closed probe budget ordering patch.

Run from repo root. Never reads/writes API credentials or runtime state.
"""
from pathlib import Path
import argparse
import ast
import os

TARGET = Path('scripts/approved_real_data_probe.py')
OLD = '''            attempt = {'id': uuid.uuid4().hex, 'started_at': now.isoformat(),
                       'status': 'INTENT'}
            history['attempts'].append(attempt)
            _atomic_write(state_path, history)
            try:
                td.reserve_request(path=budget_path, now=now)
                attempt['status'] = 'BUDGET_RESERVED'
                _atomic_write(state_path, history)
                attempt['status'] = 'REQUEST_ATTEMPTED'
'''
NEW = '''            # Stage 28: reserve budget BEFORE appending an attempt. Budget
            # rejection means no HTTP was attempted and must not poison the
            # durable probe journal with a false UNCERTAIN status. Keep the
            # probe lock throughout and still journal BEFORE network I/O.
            td.reserve_request(path=budget_path, now=now)
            attempt = {'id': uuid.uuid4().hex, 'started_at': now.isoformat(),
                       'status': 'INTENT'}
            history['attempts'].append(attempt)
            _atomic_write(state_path, history)
            try:
                attempt['status'] = 'BUDGET_RESERVED'
                _atomic_write(state_path, history)
                attempt['status'] = 'REQUEST_ATTEMPTED'
'''


def patch_source(source: str) -> str:
    if NEW in source:
        return source
    if source.count(OLD) != 1:
        raise ValueError('Expected source block missing/changed; refusing to patch')
    output = source.replace(OLD, NEW, 1)
    ast.parse(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write patched source (requires clean preflight)')
    args = parser.parse_args()
    if not TARGET.is_file() or TARGET.is_symlink():
        raise SystemExit('BLOCKED: target missing or symlink')
    source = TARGET.read_text(encoding='utf-8')
    changed = patch_source(source)
    if changed == source:
        print('ALREADY PATCHED: no changes')
        return
    if not args.apply:
        print('DRY RUN OK: Stage 28 patch compatible. Use --apply to install.')
        return
    backup = TARGET.with_suffix(TARGET.suffix + '.stage27b.backup')
    if backup.exists():
        raise SystemExit(f'BLOCKED: backup already exists: {backup}')
    # Protect existing source before replacing it. Do not overwrite backup.
    with backup.open('x', encoding='utf-8') as handle:
        handle.write(source)
        handle.flush()
        os.fsync(handle.fileno())
    TARGET.write_text(changed, encoding='utf-8')
    print(f'PATCHED: {TARGET}')
    print(f'BACKUP: {backup}')
    print('No API requests, no journal/history/credit-state changes.')


if __name__ == '__main__':
    main()
