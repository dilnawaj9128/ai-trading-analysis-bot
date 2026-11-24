Stage 55 holdout-count compatibility fix (offline; no HTTP)

Cause: Stage 55 previously required holdout['resolved'] == wins + losses + pushes.
Some Stage 29 backtest implementations use 'resolved' == wins + losses,
excluding PUSH, which is neither a win nor a loss.

Changes:
- Accept both explicitly recognized resolved-count conventions.
- Keep strict validation for malformed/negative counts and conflicting counts.
- Record the recognized convention in the statistical audit JSON.
- Never count pushes as wins or as non-push observations.
- No changes to strategy, prediction, API clients, or broker operations.

Installation from repo root:
  cp scripts/stage55_statistical_audit.py scripts/stage55_statistical_audit.py.before_count_fix
  unzip -o ~/Downloads/ai-trading-stage55-count-fix.zip
  PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage55_statistical_audit.py -q
  PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
  python -m scripts.run_stage55_robust_validation --csv data/real_market/stage52d_new_completed.csv --csv data/historical/eurusd_1min_1day.csv

The last validation command can exit with status 1 when evidence is insufficient.
NO API calls / NO orders. Reports remain in data/research/stage55.
