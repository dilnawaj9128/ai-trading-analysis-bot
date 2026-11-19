"""Apply reviewed source patch only to the exact submitted revision."""
from pathlib import Path
import hashlib, shutil, sys

root = Path(__file__).resolve().parent
project = Path.cwd()
source = project / 'market_data/manual_credit_refresh.py'
patched = root / 'market_data/manual_credit_refresh.py'
expected_sha256 = 'ae18360c74241554543e7c75ab672ffe9d9a56d2457168902926b653612ef36c'

if not source.is_file():
    raise SystemExit('Run this script from ~/ai-trading-analysis-bot')
actual = hashlib.sha256(source.read_bytes()).hexdigest()
if actual != expected_sha256:
    raise SystemExit('Source differs from uploaded review: no files modified. Re-review latest file.')

for name in ('scripts/credit_refresh_preflight.py', 'tests/test_stage22m_credit_preflight.py'):
    destination = project / name
    if destination.exists():
        raise SystemExit(f'{name} already exists: no files modified')

backup = source.with_name(source.name + '.before_stage22m.bak')
if backup.exists():
    raise SystemExit('Previous backup exists: no files modified')

shutil.copy2(source, backup)
shutil.copy2(patched, source)
for name in ('scripts/credit_refresh_preflight.py', 'tests/test_stage22m_credit_preflight.py'):
    destination = project / name
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root / name, destination)
print('Production source updated, preflight and tests installed.')
print('Backup:',backup)
