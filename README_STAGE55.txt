STAGE 55 — Robust Real-Data Prediction Audit (analysis only)

WHAT THIS PATCH DOES
- Adds exact one-sided binomial significance screening against the payout-adjusted break-even rate.
- Adds 95% Wilson confidence interval, non-push sample count, idealized units and caveats.
- Uses existing Stage 54 quality, Stage 29 historical backtest, and Stage 36 walk-forward modules.
- Writes a separate report per dataset keyed by its SHA256. No overwritten Stage 54 reports.
- Does not change production signals, credit usage, data collectors, API, or broker trading.
- DOES NOT claim a calibrated or guaranteed prediction; exploratory history is not out-of-sample future proof.

INSTALL from the project root after unzipping:
    unzip -n ~/Downloads/ai-trading-stage55-audit.zip
    source venv/bin/activate
    PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage55_statistical_audit.py -q
    PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q

REAL HISTORICAL FILES; NO NETWORK:
    python -m scripts.run_stage55_robust_validation \
      --csv data/real_market/stage52d_new_completed.csv \
      --csv data/historical/eurusd_1min_1day.csv

The CLI returns exit code 1 when results are insufficient/weak, by design.
Reports appear under data/research/stage55/<dataset>_<SHA-prefix>_stage55.json.
A green historical screening result NEVER enables a live directional trade.

For stronger estimates you need a larger, provenance-verified historical dataset
collected without selection based on results and a prospective evaluation.
The currently reported 1 and 17 resolved holdout signals are insufficient.

This patch requires the prior Stage 54 script at scripts/run_real_data_validation.py
and existing research/ and Stage 36 modules from the full project.
