#!/usr/bin/env python3
"""Create a source-only review bundle for the market-data authorization flow.

Run from ai-trading-analysis-bot repository root. Never reads .env,
credential files, data, or API state. No network requests or writes to repo.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import ast
import re
import sys

ROOT = Path.cwd().resolve()
OUTPUT = ROOT / 'bot_authorization_review.zip'
ALLOW = (
    'market_data/authorized_live_fetch.py',
    'market_data/manual_credit_refresh.py',
    'market_data/manual_refresh_preparation.py',
    'market_data/manual_refresh_execution_state.py',
    'market_data/credit_response_handler.py',
    'market_data/authorization_ledger.py',
    'market_data/unified_request_guard.py',
    'market_data/credit_refresh_store.py',
    'market_data/provider_credit_state.py',
    'market_data/twelve_data_client.py',
    'scripts/check_market_readiness.py',
)
SUSPICIOUS = re.compile(r'(?im)^\s*(?:TWELVE_DATA_API_KEY|API_KEY|SECRET|PASSWORD|TOKEN)\s*=\s*[\'\"]?[^\s#]{12,}')

if not (ROOT / 'market_data').is_dir():
    sys.exit('Run this from the project root (market_data/ not found).')

included = []
with ZipFile(OUTPUT, 'w', compression=ZIP_DEFLATED) as z:
    for rel in ALLOW:
        file = ROOT / rel
        if not file.is_file() or file.is_symlink():
            continue
        content = file.read_text(encoding='utf-8')
        ast.parse(content, filename=rel)
        if SUSPICIOUS.search(content):
            raise SystemExit(f'Possible literal credential in {rel}; bundle not safe to share. Delete {OUTPUT} and inspect it.')
        z.writestr(rel, content)
        included.append(rel)
print(f'Created: {OUTPUT}')
print(f'Source files included: {len(included)}')
print('Excluded: .env, data/api_usage, credentials, database, and other project data.')
print('Review the archive before uploading.')
