"""Offline checks for safe default reconciliation in the one-shot entrypoint."""
import inspect
from scripts.run_one_normal_fetch import fetch_one_research_snapshot


def test_verified_reconciliation_is_default():
    assert inspect.signature(fetch_one_research_snapshot).parameters['reconcile_verified'].default is True


def test_no_approval_no_http():
    import pytest
    with pytest.raises(ValueError, match='Explicit approval'):
        fetch_one_research_snapshot(approved=False, api_key='fake')


def test_no_key_no_http():
    import pytest
    with pytest.raises(ValueError, match='API key missing'):
        fetch_one_research_snapshot(approved=True, api_key=None)
