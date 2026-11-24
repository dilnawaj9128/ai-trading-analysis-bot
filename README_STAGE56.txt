STAGE 56: BASELINE FAILURE AUDIT (RESEARCH ONLY)

Files added:
 scripts/stage56_failure_analysis.py
 scripts/run_stage56_failure_analysis.py
 tests/test_stage56_failure_analysis.py

Does not overwrite any existing project code. No HTTP, no API key use, no broker orders, no strategy optimization.

Install from your project root:
 unzip -n ~/Downloads/ai-trading-stage56-failure-audit.zip

Offline tests:
 PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q

Run on both real datasets:
 python -m scripts.run_stage56_failure_analysis \
   --csv data/real_market/stage52d_new_completed.csv \
   --csv data/historical/eurusd_1min_1day.csv

Reports: data/research/stage56/<dataset>_<source hash>_failures.json

Outputs group-level descriptive wins/losses/pushes and prior-20-candle trend/range regimes. Only holdout trades count. A baseline trade log is produced by the preexisting research.stage29_backtest.backtest. Stops if unexpected outcome, overlapping 15-minute trades, invalid data or mismatched outcome counts occur. Never promote a group with fewer than 10 nonpush outcomes as interpretable.

LIMITATIONS:
- The project archive provided previously omitted research/, analysis/, strategy/ and real data, so complete integration and real-market performance cannot be verified in the assistant runtime. Please run full tests and offline CLI in the complete local project.
- Stage 56 is a failure diagnosis, NOT a proven accuracy improvement. Do not select new trading filters based on the same holdout data: any future modifications must be frozen and evaluated on NEW chronological holdout and prospective data.
- Historical close-based 15m settlements are research results, not verified Quotex trading prices; live direction stays NO TRADE when feed parity is unverified.
