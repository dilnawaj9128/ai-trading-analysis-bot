# Stage 27A — Smart Start cooldown fix

This patch updates the Stage 27 dashboard page and adds one read-only preflight helper.
The existing `scripts/approved_real_data_probe.py` is NOT changed. Its persistent
180-second cooldown, file lock, local credit budget, and unresolved-attempt
protection remain the final authority for any API request.

## Install

From the repository root, after extracting the ZIP:

```bash
cp dashboard/pages/9_Real_Data_Research.py dashboard/pages/9_Real_Data_Research.py.stage27.bak
cp stage27a/dashboard/pages/9_Real_Data_Research.py dashboard/pages/
cp stage27a/dashboard/live_probe_readiness.py dashboard/
cp stage27a/tests/test_stage27a_smart_start.py tests/
```

## Verify without an API call

```bash
env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage27a_smart_start.py -q
env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
```

## Behavior

- Live Analysis OFF by default. Starting requires explicit browser approval.
- If the previous probe is `VERIFIED` but younger than 180 s, show
  `WAITING_FOR_COOLDOWN`. No HTTP or budget use during the wait.
- The browser refresh tick checks every 15 s (with Streamlit `st.fragment`),
  so actual execution may lag expiry by up to ~15 s.
- If the probe is ready, first request attempts immediately (the timer tick
  runs after the Streamlit rerun).
- Maximum 3 real requests total including the first; 60-minute session cap.
- A prior unresolved attempt or invalid probe history BLOCKS, with no retry.
- `data_mode="unknown"` remains: official UP/DOWN signals are not enabled
  until independent provider feed-mode verification is implemented. Indicator
  alignment is exploratory only. No broker execution.

## Notes

This updates the browser-session UI. It does not guarantee reliability across
browser disconnects or host restarts, and is not a 24/7 daemon.
Do not delete `data/api_usage/approved_research_probe.json` or attempt to
set `UNCERTAIN` states to `VERIFIED` manually.
