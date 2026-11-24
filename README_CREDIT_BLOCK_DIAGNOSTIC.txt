STREAMLIT VERIFIED CREDIT RENEWAL — SAFE BLOCKER DIAGNOSTIC

This patch adds a read-only reason panel to the existing Auto Live Monitor.
It DOES NOT remove or reconcile existing reservations or historical UNCERTAIN attempts.
It DOES NOT request additional API credits or change the credit freshness policy.

Install from repository root:
  cp dashboard/pages/4_Auto_Live_Monitor.py dashboard/pages/4_Auto_Live_Monitor.py.before_diag
  unzip -o ~/Downloads/ai-trading-credit-block-diagnostic.zip
  PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
  python -m streamlit run dashboard/app.py

Open Auto Live Monitor. Read the "Credit renewal preflight" warning before any
additional one-shot approval. If it shows BLOCKED/UNKNOWN, do not click Fetch.
The diagnostic is preliminary, never a grant of authorization; other guards
can still prevent a fetch. Preserve original state files for accounting review.
