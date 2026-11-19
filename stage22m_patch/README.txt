STAGE 22M — Controlled Twelve Data refresh preflight hardening

Changes:
- Harden existing production manual_credit_refresh.py: reject prior authorization evidence,
  repeated refresh claims, invalid/exhausted local budget, before any new claim.
- Disallow request redirects; require HTTP 200 from Twelve Data.
- Add no-network read-only preflight command and five tests.
- No API request is executed by installation or tests. No changes to your quota files.

HOW TO APPLY ON UBUNTU:
  cd ~/ai-trading-analysis-bot
  unzip ~/Downloads/bot_credit_refresh_patch.zip -d stage22m_patch
  python stage22m_patch/apply_patch.py
  env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage22m_credit_preflight.py -q
  env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
  PYTHONPATH="$PWD" python scripts/credit_refresh_preflight.py

The preflight only reports eligibility for a single explicitly approved refresh.
It DOES NOT enable live fetching or release pending/uncertain reservations.
Do not remove claims or overwrite production state to force the result to PASS.

We have not executed your full repository suite because the ZIP contained only 11 files.
