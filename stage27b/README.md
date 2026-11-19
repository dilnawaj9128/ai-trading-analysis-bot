# Stage 27B — Timeout diagnostics and offline recovery report

This patch uses the uploaded `scripts/approved_real_data_probe.py` as its base.

## Changes
- Keep `approved=True`, three-minute cooldown, locking, quota reservation, and fail-closed `UNCERTAIN` lifecycle unchanged.
- For **future** approved requests, requests uses `(connect_timeout=5s, read_timeout=30s)` rather than one 15-second timeout. This does **not** guarantee success and cannot settle an old request.
- For **future** failures, record only safe `failure_category` and UTC failure time in probe history. Existing `UNCERTAIN` attempts remain untouched.
- Add `scripts/probe_recovery_report.py`: reads history, CSV, and provider snapshot locally; does not call HTTP or alter any state. Even if file timestamps changed, it never declares reconciliation.

## Install from repository root
```bash
cd ~/ai-trading-analysis-bot
source venv/bin/activate
unzip -o ~/Downloads/stage27b_timeout_recovery.zip
cp scripts/approved_real_data_probe.py scripts/approved_real_data_probe.py.stage27a.bak
cp stage27b/scripts/approved_real_data_probe.py scripts/
cp stage27b/scripts/probe_recovery_report.py scripts/
cp stage27b/tests/test_stage27b_recovery_report.py tests/
```

## Run offline tests and read-only report
```bash
env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage27b_recovery_report.py -q
env -u TWELVE_DATA_API_KEY python -m pytest tests/test_approved_real_data_probe.py -q
python scripts/probe_recovery_report.py
```

## Safety note
The currently reported Nov 19 `UNCERTAIN` request **cannot** be proven resolved using only local CSV and snapshot timestamps. This patch **does not** clear the lockout or allow an automatic retry. It does not issue any HTTP requests when installed, tested or when the recovery report is run. Request reconciliation requires trusted provider-side evidence and a separately designed, audited recovery process.
