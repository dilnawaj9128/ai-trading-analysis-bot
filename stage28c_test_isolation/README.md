# Stage 28C test isolation correction

The 16 test failures were caused by legacy mocked-fetch tests reading your production `data/api_usage/approved_research_probe.json` (last attempt `UNCERTAIN`).

Install **only** `tests/conftest.py` after checking there is no pre-existing `tests/conftest.py` (or merge the fixture with the existing one). The fixture uses pytest's temporary test directory for **five specific mock-based test modules** and monkeypatches the gate's default probe-state path only while those tests execute. It does not bypass any guard in production or change a JSON state file.

Commands from repository root:

```bash
unzip -o ~/Downloads/stage28c_test_isolation.zip
# Do not overwrite an existing tests/conftest.py without reviewing it.
test ! -e tests/conftest.py && cp stage28c_test_isolation/tests/conftest.py tests/
env -u TWELVE_DATA_API_KEY python -m pytest tests/test_authorized_live_fetch.py tests/test_authorized_live_integration.py tests/test_stage22j_live_failure.py tests/test_stage22l_production_refresh.py tests/test_twelve_data_client.py tests/test_stage28c_gate.py -q
env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
```

If `tests/conftest.py` already exists, do not overwrite; paste its contents so the fixture can be merged safely.
