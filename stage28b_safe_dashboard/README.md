Stage 28B — Read-only signal freshness fix and fetch path inventory.

From repository root:
  unzip -o ~/Downloads/stage28b_safe_dashboard.zip
  python stage28b_safe_dashboard/scripts/apply_stage28b.py --apply
  python -m pytest stage28b_safe_dashboard/tests/test_stage28b_dashboard.py -q
  python stage28b_safe_dashboard/scripts/audit_live_fetch_paths.py
  env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q

The patch backs up dashboard/pages/9_Real_Data_Research.py and only replaces its final static signal display block. It does NOT change the provider fetch logic, probe journal, historical evidence, API credit state, or feed trust flags. The signal panel reruns every 30 seconds when Streamlit supports fragments, rereads local CSV, and becomes NO TRADE when stale/invalid. Market price metrics and chart remain main-page snapshots until next app rerun.

The inventory is diagnostic, not a fix for legacy independent API paths. Do not enable legacy monitors while the unresolved request remains UNCERTAIN.
