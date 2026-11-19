Stage 25: manual approved real market refresh inside existing dashboard page.

Install from project root (back up the current page first):
  cp dashboard/pages/9_Real_Data_Research.py dashboard/pages/9_Real_Data_Research.py.stage24.bak
  cp stage25/dashboard/pages/9_Real_Data_Research.py dashboard/pages/

The existing scripts/approved_real_data_probe.py MUST be present, as it was
already used successfully in your project. This page imports and calls
probe_once(approved=True) ONLY when the explicit approve checkbox is checked
and the user clicks the one-request button.

The page displays saved candles without any HTTP. The preferred refresh
interval is informational only; there is no automatic polling.

The probe persists history in data/api_usage/approved_research_probe.json,
reserves local budget and enforces a 180-second cooldown. Do NOT delete state
files to force retries. The previous manual refresh approval remains consumed.

The dashboard must be started with TWELVE_DATA_API_KEY already loaded into its
environment. Do not share keys or commit .env.

Tests:
  python -m pytest stage25/tests/ -q
  env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q

Launch:
  PYTHONPATH="$PWD" python -m streamlit run dashboard/app.py

Real API requests only on button click with checkbox; may consume API credits.
No broker parity, directional accuracy or automatic trading is claimed.
