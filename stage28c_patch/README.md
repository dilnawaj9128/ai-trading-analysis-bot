# Stage 28C — Cross-path probe safety gate (offline)

The user currently has an `UNCERTAIN` attempt in `data/api_usage/approved_research_probe.json`.
This patch ensures three additional production fetching functions check that history
**before** provider authorization/budget reservations/HTTP calls:

- `market_data/authorized_live_fetch.py` → `fetch_authorized_live_candles`
- `market_data/twelve_data_client.py` → `fetch_recent_candles`
- `market_data/manual_credit_refresh.py` → `refresh_production_provider_credits`

The approved probe already holds an exclusive lock on its `.lock` file. Other
production fetches now use a shared lock across their full function call and
refuse an `UNCERTAIN`, incomplete, corrupt or implausibly timestamped probe
history. The existing approved probe code is **not changed**.

This is only a **cross-path veto**, not a comprehensive merging of the three
independent authorization protocols. Existing authorizations, credit limits,
explicit consent and timeout protections remain separate.

## Install (from repo root, with venv activated)

```bash
unzip -o ~/Downloads/stage28c_api_gate.zip
cp stage28c_patch/market_data/probe_cross_path_gate.py market_data/
python stage28c_patch/scripts/apply_stage28c.py   # safe dry run
python stage28c_patch/scripts/apply_stage28c.py --apply
cp stage28c_patch/tests/test_stage28c_gate.py tests/
```

The installer creates `.stage28c.bak` source backups and refuses already
occupied backup paths. It is idempotent after a successful installation.

## Test

```bash
python -m pytest tests/test_stage28c_gate.py -q
env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
```

These local tests make no Twelve Data requests. Existing tests that perform a
mocked production fetch without isolating the real `data/api_usage` folder may
need an isolated working directory: the new veto deliberately blocks such
calls when production probe history is `UNCERTAIN`. Do not delete/alter that
history to make tests pass. Report failures instead.

## Scope limitations

- No request reconciliation is performed. The old uncertain attempt remains.
- Some other/non-production HTTP call sites might exist; this gate covers the
  three named production entrypoints, not every possible HTTP call in the repo.
- Holding the shared gate lock while HTTP is in flight blocks concurrent probe
  attempts for the duration. This is intentional to prevent interleaving.
- Last status `VERIFIED` means only that this *particular veto* allows passing;
  the normal per-path budget/provider/approval checks still decide authorization.
- This patch does not improve prediction accuracy or guarantee feed parity.
