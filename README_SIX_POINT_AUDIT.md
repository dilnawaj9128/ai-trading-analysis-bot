# Regular EUR/USD six-point evidence audit

This addition audits six research and deployment goals **without making HTTP requests, reading API keys, modifying credit-accounting journals, placing broker orders, or tuning a strategy**.

## Run

From the project root (venv already active):

```bash
PYTHONPATH="$PWD" python -m pytest tests/test_eurusd_six_point_audit.py -q
PYTHONPATH="$PWD" python -m scripts.run_eurusd_six_point_audit
```

It creates a **new report** in `reports/eurusd_six_point_evidence_*.json`. Existing reports are not overwritten.

## Task interpretation

1. Official Twelve Data regular EUR/USD Forex catalog class: real-time composite. **Account-specific live/delayed entitlement and original response are NOT attested by a CSV**. Earlier support replies also indicate no documented `feed_mode` field for `time_series`.
2. Unseen predictive accuracy: requires chronologically recorded directional predictions before settlement; historical backtest samples are deliberately excluded from forward accuracy.
3. Sample size: reports exact nonpush outcomes against an initial minimum of 100. Does not manufacture outcomes, or lower the bar.
4. Statistical edge: uses the existing Wilson interval and exact binomial screen; even a screen passing is not real executable profitability proof.
5. Monitoring: virtual 24-hour **policy** simulation checks 3-attempt cap and failure-stop. It is **not 24 hours of real API data or service uptime**.
6. Deployment: validates local entrypoint presence and required Python imports. It is not proof of a remotely deployed, secured, always-on production environment.

This report is a gap assessment, not a shortcut to declaring the unresolved tasks complete.

**Baseline (2026-11-24 user terminal outputs):** 1471 tests passed before this patch; saved 120-candle EUR/USD snapshot, 0 gaps; 6 prospective NO TRADE observations (3 ABSTAINED, 3 pending), 0 directional wins/losses; older 1440-candle historical backtest 17 nonpush and 41.18% wins; 18 outstanding conservative local reservations. These historical figures are **not hardcoded as passing metrics** in the script; every run reads local current evidence.

**Security:** Do not fabricate a `live` mode or bypass credit guard; do not consider data freshness a provider entitlement receipt; do not restart a failed/uncertain API request automatically; no strategy orders.
