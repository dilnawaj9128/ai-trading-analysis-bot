"""Offline checks for bounded immediate-first-fetch policy and page wiring."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.auto_refresh_policy import (
    MAX_CALLS, due_for_refresh, finish_attempt, start_auto_refresh,
)

T = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def test_initial_approval_is_single_counted_attempt():
    session = start_auto_refresh(now=T, minutes=3, approved=True)
    staged = finish_attempt(session, now=T, successful=True)
    assert staged['attempts'] == 1
    assert not due_for_refresh(staged, now=T)
    assert not due_for_refresh(staged, now=T + timedelta(minutes=2, seconds=59))
    assert due_for_refresh(staged, now=T + timedelta(minutes=3))


def test_total_three_requests_including_immediate():
    session = start_auto_refresh(now=T, minutes=3, approved=True)
    for minute in (0, 3, 6):
        session = finish_attempt(session, now=T + timedelta(minutes=minute), successful=True)
    assert session['attempts'] == MAX_CALLS == 3
    assert session['active'] is False


def test_failure_pauses_without_retries():
    session = start_auto_refresh(now=T, minutes=3, approved=True)
    session = finish_attempt(session, now=T, successful=False)
    assert not due_for_refresh(session, now=T + timedelta(minutes=10))


def test_page_compiles_and_reuses_probe():
    source = Path(__file__).resolve().parents[1].joinpath(
        'dashboard/pages/9_Real_Data_Research.py'
    ).read_text()
    ast.parse(source)
    assert 'Start Live Analysis — fetch now' in source
    assert 'response = approved_refresh_once()' in source
    assert 'data_mode="unknown"' in source
    assert 'execution_enabled=True' not in source
