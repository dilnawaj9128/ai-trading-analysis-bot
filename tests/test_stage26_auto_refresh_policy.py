from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path
import unittest
from dashboard.auto_refresh_policy import (
    start_auto_refresh, due_for_refresh, finish_attempt, MAX_CALLS,
)

T = datetime(2026, 11, 18, 19, 0, tzinfo=timezone.utc)


class TestAutoPolicy(unittest.TestCase):
    def test_opt_in_required(self):
        with self.assertRaises(ValueError):
            start_auto_refresh(now=T, minutes=3, approved=False)

    def test_due_only_after_interval(self):
        s = start_auto_refresh(now=T, minutes=3, approved=True)
        self.assertFalse(due_for_refresh(s, now=T + timedelta(seconds=179)))
        self.assertTrue(due_for_refresh(s, now=T + timedelta(minutes=3)))

    def test_finite_cap(self):
        s = start_auto_refresh(now=T, minutes=3, approved=True)
        for i in range(MAX_CALLS):
            t = T + timedelta(minutes=3 * (i + 1))
            self.assertTrue(due_for_refresh(s, now=t))
            s = finish_attempt(s, now=t, successful=True)
        self.assertFalse(s['active'])
        self.assertFalse(due_for_refresh(s, now=T + timedelta(minutes=30)))

    def test_fail_stops(self):
        s = start_auto_refresh(now=T, minutes=5, approved=True)
        s = finish_attempt(s, now=T + timedelta(minutes=5), successful=False)
        self.assertFalse(due_for_refresh(s, now=T + timedelta(minutes=20)))

    def test_session_expires(self):
        s = start_auto_refresh(now=T, minutes=15, approved=True)
        self.assertFalse(due_for_refresh(s, now=T + timedelta(minutes=60)))

    def test_no_api_import_in_policy_and_page_compiles(self):
        p = Path(__file__).resolve().parents[1] / 'dashboard/pages/9_Real_Data_Research.py'
        ast.parse(p.read_text())
        source = (Path(__file__).resolve().parents[1] / 'dashboard/auto_refresh_policy.py').read_text()
        self.assertNotIn('requests', source)
        self.assertNotIn('probe_once', source)


if __name__ == '__main__':
    unittest.main()
