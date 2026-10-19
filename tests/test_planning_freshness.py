"""Read-only planning freshness and replay protection."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from dashboard_feed import snapshot
from read_only_planning import ReadOnlyPlanningSession
from test_read_only_planning import caps, frame


def live(tick=120):
    c = caps()
    c["tick"] = tick
    return dict(status="ok", **snapshot(dict(frame(), tick=tick, capabilities=c)))


class FreshnessGateTests(unittest.TestCase):
    def test_repeated_tick_stale_then_new_tick_recovers(self):
        session = ReadOnlyPlanningSession(max_still_seconds=5)
        self.assertTrue(session.observe(live(), now=100)["planner_ready"])
        self.assertTrue(session.observe(live(), now=104)["planner_ready"])
        result = session.observe(live(), now=106)
        self.assertFalse(result["planner_ready"])
        self.assertEqual(result["status"], "stale")
        self.assertTrue(session.observe(live(121), now=107)["planner_ready"])

    def test_tick_regression_and_clock_regression_rejected(self):
        session = ReadOnlyPlanningSession(max_still_seconds=5)
        session.observe(live(), now=100)
        with self.assertRaisesRegex(ValueError, "tick regressed"):
            session.observe(live(119), now=101)
        with self.assertRaisesRegex(ValueError, "clock regressed"):
            session.observe(live(), now=99)

    def test_disconnection_clears_freshness_and_restarts_safely(self):
        session = ReadOnlyPlanningSession(max_still_seconds=5)
        session.observe(live(), now=100)
        result = session.observe({"status": "unavailable"}, now=110)
        self.assertFalse(result["planner_ready"])
        self.assertTrue(session.observe(live(119), now=120)["planner_ready"])

    def test_invalid_max_still_age_refused(self):
        for bad in (float("nan"), 0, -1, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ReadOnlyPlanningSession(max_still_seconds=bad)
