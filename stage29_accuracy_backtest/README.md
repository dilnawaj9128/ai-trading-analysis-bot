# Stage 29 — Offline 15-minute prediction accuracy backtest

Additive files only. No existing files, API state, journal, or dashboard overwritten.

From the project root, unzip the archive and install:

```bash
cp -r stage29_accuracy_backtest/research .
cp stage29_accuracy_backtest/scripts/run_stage29_backtest.py scripts/
cp stage29_accuracy_backtest/tests/test_stage29_backtest.py tests/
PYTHONPATH="$PWD" python -m pytest tests/test_stage29_backtest.py -q
PYTHONPATH="$PWD" python scripts/run_stage29_backtest.py
```

The current 120-candle CSV is **too small for credible out-of-sample accuracy** and may produce 0 signals. More historical candles are needed before drawing conclusions. No API requests occur in this version. It runs your existing indicator and strategy modules in *offline research mode only* and does not change the live signal engine's unknown-feed guard.

Method: at close of candle i, calculate only from candles <= i; hypothetical entry at close i; 15 one-minute bars later settle at close i+15. This is an optimistic fill assumption; live binary outcomes may differ. No overlapping signal trades by default. 70/30 chronological split, no training outcomes crossing the split. Gaps in the 60-candle lookback or settlement period skip the sample. Win rate ignores PUSH; net unit P&L assumes specified fixed payout on wins and full 1-unit loss on losses. False precision is avoided by warning below 30 resolved holdout signals.

**Known limitations**: Historical indicator decisions can differ from a streaming client using provider-specific revisions. Existing `generate_signal` uses EMA/RSI/MACD etc. Quotex feed parity and actual execution prices are not verified. Results do not authorize real-money trades. No automatic parameter optimization or claim of predictive skill.
