# Stage 28 — Safe Budget Reservation Ordering

This source-only patch moves `td.reserve_request` ahead of adding a probe-attempt record, while keeping the same exclusive probe lock. If the local budget rejects a request, the durable probe history is not incorrectly marked `UNCERTAIN`. After successful reservation, the attempt still gets journaled before any HTTP request. If anything fails after reservation, existing fail-closed `UNCERTAIN` handling stays in effect.

No changes are made to account usage, API key, data files, existing request records, the unresolved 19 Nov attempt, or monitoring authorization paths. This patch does not unlock live API requests.

Run from project root:

```bash
cd ~/ai-trading-analysis-bot
source venv/bin/activate
unzip -o ~/Downloads/stage28_safe_budget_fix.zip
python stage28_safe_budget_fix/scripts/apply_stage28_patch.py
python stage28_safe_budget_fix/scripts/apply_stage28_patch.py --apply
cp stage28_safe_budget_fix/tests/test_stage28_safe_budget_patch.py tests/
env -u TWELVE_DATA_API_KEY python -m pytest tests/test_stage28_safe_budget_patch.py -q
env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
```

The patch refuses unknown source layout and pre-existing backup instead of overwriting them. The backup is `scripts/approved_real_data_probe.py.stage27b.backup`. Do NOT delete/change `data/api_usage/approved_research_probe.json`: the existing request remains UNCERTAIN until provider evidence is reviewed.

This corrects one specific pre-HTTP failure path. The full codebase may have other request flows with distinct safety policies, and previous tests passing do not prove trading strategy accuracy or feed parity.
