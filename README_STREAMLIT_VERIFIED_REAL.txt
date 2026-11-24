STREAMLIT VERIFIED REAL DATA - LOCAL PATCH

Files:
  dashboard/pages/4_Auto_Live_Monitor.py
  dashboard/verified_live_control.py
  tests/test_verified_live_dashboard_control.py

Goal: Preserve existing Streamlit Auto Live Monitor and add an independent
manual one-shot real EUR/USD research fetch with optional verified credit
renewal. The new button is intentionally available even when the old auto
monitor Start button is disabled due to an expired credit snapshot.

SAFETY:
- User must check an opt-in box and click the button themselves.
- Up to 2 separately-accounted Twelve Data HTTP requests per click.
- No automatic retries or background looping for this new button.
- Existing UNCERTAIN records, reservations, provider snapshots, and API
  guard modules are not changed by installation.
- The button reuses scripts.run_one_normal_fetch.fetch_one_research_snapshot
  and market_data.live_analysis_bridge, both already on the user's laptop.
- No broker orders. The unverified Quotex parity signal remains NO TRADE.
- On failures, do NOT click the button again until accounting is reviewed.

Install on Ubuntu:
  cd ~/ai-trading-analysis-bot
  source venv/bin/activate
  cp dashboard/pages/4_Auto_Live_Monitor.py dashboard/pages/4_Auto_Live_Monitor.py.before_verified_real
  unzip -o ~/Downloads/ai-trading-streamlit-real-fix.zip
  PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q

Launch Streamlit from project root with local API key loaded by the
new one-shot control from .env. Do not paste the key in chat:
  python -m streamlit run dashboard/app.py

Navigate to Auto Live Monitor -> Verified EUR/USD real-data research.
Check the explicit approval box and click Fetch & analyze once only when
ready to spend up to 2 credits. Old auto-monitor remains disabled on stale
credits unless separately reconciled; this does NOT make it silently auto-refresh.

External research needs larger independent samples for accuracy validation.
