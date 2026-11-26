PRIORITY 3 — ATTESTED OFFLINE EUR/USD ANALYSIS (Stage A)
=====================================================

Install in project root:
  unzip -n ~/Downloads/ai-trading-priority3.zip

Run offline tests, no HTTP:
  PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/test_priority3_analysis.py -q

Run actual existing RSI/EMA/MACD/ATR + pattern + signal pipeline using
SHA-256 verified Stage52D saved completed candles:
  python -m scripts.run_priority3_analysis

The script:
- Verifies Stage52D recovery's original evidence, journal, authorization
  and hash of saved CSV with existing verified_recovery_override.
- Uses existing scripts.analyze_saved_real_candles analyzer (requires
  user's own analysis/ and strategy/ project folders).
- Shows indicators, market condition, data freshness, gap count and reasons.
- Returns NO TRADE because Twelve Data feed is not verified as the broker's
  live quote source. This is deliberate; not a model-accuracy guarantee.
- Makes ZERO HTTP requests and ZERO credit reservations; doesn't modify
  the source evidence or use a broker.
- Saved older data will report stale=True, which is expected.

This is Priority 3's safe offline integration, NOT full live monitoring or
proven trading performance. Future live monitoring would require separate
opt-in request accounting and snapshot persistence, with no automatic retries.
