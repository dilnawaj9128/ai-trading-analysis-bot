# Stage 27: live research session (manual opt-in)

This patch modifies only `dashboard/pages/9_Real_Data_Research.py` and adds
`tests/test_stage27_live_session.py`. It uses your existing
`scripts/approved_real_data_probe.py` and `dashboard/auto_refresh_policy.py`
unchanged.

- Start Live Analysis triggers **one immediate request** after explicit approval.
- At most **three total API attempts**, including the immediate request, with
  the remaining attempts separated by a minimum three-minute interval.
- Every API attempt uses the existing probe budget, durable evidence and
  cooldown. If that probe blocks/fails, auto session stops; no automatic retry.
- The browser must remain connected; there is no separate background daemon.
- Feed mode stays **unverified**: official UP/DOWN strategy signal will remain
  NO TRADE. A separate indicator-only bias appears when data are recent and
  technically aligned. Do not treat the bias as a Quotex prediction.
- No broker connection or trade execution.

## Installation

```bash
cd ~/ai-trading-analysis-bot
source venv/bin/activate
cp dashboard/pages/9_Real_Data_Research.py dashboard/pages/9_Real_Data_Research.py.stage26.bak
cp stage27_live_analysis/dashboard/pages/9_Real_Data_Research.py dashboard/pages/
cp stage27_live_analysis/tests/test_stage27_live_session.py tests/
env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage27_live_session.py -q
env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
set -a; source .env; set +a
PYTHONPATH="$PWD" python -m streamlit run dashboard/app.py
```

Do not delete existing `data/api_usage` files; do not execute tests with real
API credentials. This patch has no new HTTP request at installation time.
