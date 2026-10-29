"""The read-only observer must wait for its owned game before starting MCP."""
import sys
import unittest
from importlib import util
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "agent")]


class ObserverReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_is_not_started_before_the_game_endpoint_is_ready(self):
        if util.find_spec("mcp") is None:
            self.skipTest("MCP test dependency unavailable")
        import live_r10b_observer_stress as harness

        observer = harness.InventoryObserver(29999, "not-a-real-secret", ROOT / ".local" / "unused-probe")
        with patch.object(harness.r10a, "_wait_for_rcon", new=AsyncMock(return_value=False)) as ready:
            with patch("mcp.client.stdio.stdio_client") as backend:
                with self.assertRaisesRegex(RuntimeError, "never became ready"):
                    await observer._drive()
                backend.assert_not_called()
                ready.assert_awaited_once_with(29999)


class ObserverVerdictTests(unittest.TestCase):
    def test_no_requests_or_an_unstopped_worker_cannot_pass(self):
        import live_r10b_observer_stress as harness

        report = {"requests": 1, "failures": 0, "timeouts": 0, "error": None,
                  "pages_unique": True, "worker_stopped": True}
        self.assertTrue(harness.observer_pass(report))
        for key, value in (("requests", 0), ("failures", 1), ("timeouts", 1),
                           ("pages_unique", False), ("worker_stopped", False)):
            self.assertFalse(harness.observer_pass(dict(report, **{key: value})))
