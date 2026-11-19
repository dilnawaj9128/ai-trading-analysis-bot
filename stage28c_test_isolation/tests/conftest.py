"""Stage 28C: isolate legacy mocked-fetch tests from real user probe history.

Only existing unit/integration test modules that exercise injected fake HTTP
clients are scoped. Production code and on-disk probe history are unchanged.
The dedicated Stage 28C gate tests still exercise the real guard behavior
with their own intentionally constructed test histories.
"""

from pathlib import Path

import pytest


_LEGACY_MOCKED_FETCH_TESTS = frozenset({
    "test_authorized_live_fetch.py",
    "test_authorized_live_integration.py",
    "test_stage22j_live_failure.py",
    "test_stage22l_production_refresh.py",
    "test_twelve_data_client.py",
})


@pytest.fixture(autouse=True)
def _stage28c_isolate_mocked_fetch_tests(request, tmp_path, monkeypatch):
    """Give selected offline tests a nonexistent temporary probe history.

    No bypass in production: monkeypatch restores the original value after each
    test. Other tests (including test_stage28c_gate) are unaffected.
    """
    if Path(str(request.node.fspath)).name not in _LEGACY_MOCKED_FETCH_TESTS:
        return
    from market_data import probe_cross_path_gate

    monkeypatch.setattr(
        probe_cross_path_gate,
        "PROBE_STATE",
        tmp_path / "isolated_test_probe_history.json",
    )
