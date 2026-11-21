STAGE 54 — Real-data pre-dashboard research validation

Unzip into ~/ai-trading-analysis-bot with: unzip -n ~/Downloads/ai-trading-real-validation.zip

1. Test existing project:
   env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
2. Audit ALREADY SAVED actual Twelve Data completed candles (no API calls):
   python -m scripts.run_real_data_validation --csv data/real_market/stage52d_new_completed.csv
3. For useful historical walk-forward evaluation, supply a longer legitimate, continuous 1min dataset:
   python -m scripts.run_real_data_validation --csv data/historical/eurusd_1min_1day.csv

The command exits 1 when historical proof is INSUFFICIENT_DATA and 2 if blocked/error.
A 120-candle snapshot cannot independently establish reliable 15-min prediction accuracy.
Research may report an exploratory backtest, but actual Quotex-compatible UP/DOWN prediction remains disabled unless feed parity is independently validated.
No automatic provider API calls and no broker orders; do not rerun a previously uncertain API fetch.
