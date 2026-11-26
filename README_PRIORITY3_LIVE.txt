Priority 3: in-memory real-fetch-to-existing-analysis integration

AUDIT: The uploaded project already contains these existing components:
  market_data/live_monitor.py (1/3/5-minute single-machine poll reservation)
  scripts/analyze_saved_real_candles.py (offline engine)
  analysis.live_engine, analysis.smart_market, strategy.signal_engine (referenced by code and tests; not in supplied archive)
  scripts/run_one_normal_fetch.py (live authorized fetch and conditional verified credit renewal)

CHANGED: scripts/run_one_normal_fetch.py
NEW: market_data/live_analysis_bridge.py
NEW: tests/test_live_analysis_bridge.py

Safety: The added analysis uses the SAME in-memory DataFrame returned from one authorized normal fetch. No second request for analytics, no file mutations or orders. Direction remains NO TRADE until provider/broker feed parity is independently attested.

Install on user's Ubuntu laptop:
  cd ~/ai-trading-analysis-bot
  source venv/bin/activate
  cp scripts/run_one_normal_fetch.py scripts/run_one_normal_fetch.py.before_priority3
  unzip -o ~/Downloads/ai-trading-priority3-live-bridge.zip
  PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
  python -m scripts.run_one_normal_fetch --analyze

The last command is PREVIEW ONLY: zero requests. It is not necessary to issue another real API request to verify this offline code. A new request requires an explicit approval flag AND a fresh budget/snapshot guard, and must never be repeated after a failure without inspecting journals.

When the user intentionally approves at most two fresh Twelve Data requests/credits:
  python -m scripts.run_one_normal_fetch --approve-up-to-two-requests --analyze

This may be denied if an earlier renewal is unresolved, stale verified credit evidence is older than 24h, or local/provider budgets don't permit. Do not delete state files or force timestamps. No guarantees about prediction accuracy.
