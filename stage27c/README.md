# Stage 27C — Offline Reconciliation Checklist

This patch adds one read-only command. It **does not** reconcile an uncertain attempt, approve a retry, request an API credit, or modify any existing state file.

## Install (from project root)

```bash
unzip -o ~/Downloads/stage27c_reconciliation_checklist.zip
cp stage27c/scripts/probe_reconciliation_check.py scripts/
cp stage27c/tests/test_stage27c_reconciliation_check.py tests/
```

Requires existing Stage 27B `scripts/probe_recovery_report.py`.

## Check

```bash
env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage27c_reconciliation_check.py -q
python scripts/probe_reconciliation_check.py
```

The report contains a UTC comparison window around the last probe attempt, whether local CSV and cached credit snapshot were written after that attempt, and a checklist for checking provider-side usage. Those timestamps **cannot prove** whether the provider charged the uncertain request. Never delete/overwrite `data/api_usage/approved_research_probe.json` or manually mark an uncertain attempt verified.

No API key or provider credentials are needed for this inspection.
