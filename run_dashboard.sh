#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT"
if [[ ! -x venv/bin/python ]]; then
  echo 'Missing virtualenv: create venv and install original project dependencies first' >&2
  exit 2
fi
# Never log keys. Streamlit reads local .env only when an explicitly approved fetch runs.
exec "$PROJECT/venv/bin/python" -m streamlit run "$PROJECT/dashboard/app.py" \
  --server.address 127.0.0.1 --server.port "${STREAMLIT_PORT:-8501}" \
  --browser.gatherUsageStats false
