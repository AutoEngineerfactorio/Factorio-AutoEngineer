"""Offline safety regressions for the single-game-instance performance governor."""
import sys
import unittest
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from performance_governor import (  # noqa: E402
    UPSGuard,
    owned_process_creationflags,
)


class UPSGuardTests(unittest.TestCase):
    def test_unknown_is_conservative_and_does_not_claim_sixty_ups(self):
        guard = UPSGuard()
        self.assertIsNone(guard.budget().estimated_ups)
        self.assertFalse(guard.budget().ai_allowed)
        self.assertFalse(guard.budget().catalog_allowed)

    def test_stable_game_requires_multiple_readings_to_admit_ai(self):
        guard = UPSGuard()
        for i in range(4):
            budget = guard.observe(i * 300, i * 5.0)
        self.assertEqual(budget.state, "healthy")
        ups = budget.estimated_ups
        assert ups is not None
        self.assertAlmostEqual(ups, 60.0)
        self.assertTrue(budget.ai_allowed)
        self.assertEqual(budget.min_ai_seconds, 8.0)

    def test_degraded_game_pauses_optional_work(self):
        guard = UPSGuard()
        for i in range(4):
            guard.observe(i * 300, i * 5.0)
        guard.observe(1180, 20.0)
        budget = guard.observe(1460, 25.0)
        self.assertEqual(budget.state, "degraded")
        self.assertFalse(budget.ai_allowed)
        self.assertFalse(budget.catalog_allowed)
        self.assertGreaterEqual(budget.telemetry_seconds, 5)

    def test_severe_slowdown_stops_ai_immediately(self):
        guard = UPSGuard()
        guard.observe(0, 0.0)
        result = guard.observe(100, 5.0)
        self.assertEqual(result.state, "critical")
        self.assertFalse(result.ai_allowed)

    def test_paused_game_is_not_called_healthy(self):
        guard = UPSGuard()
        guard.observe(200, 0)
        result = guard.observe(200, 5)
        self.assertEqual(result.state, "critical")

    def test_recovery_needs_multiple_good_windows(self):
        guard = UPSGuard()
        guard.observe(0, 0)
        guard.observe(100, 5)
        self.assertEqual(guard.state, "critical")
        guard.observe(400, 10)
        guard.observe(700, 15)
        self.assertEqual(guard.state, "critical")
        guard.observe(1000, 20)
        self.assertEqual(guard.state, "healthy")

    def test_out_of_order_clock_does_not_create_health(self):
        guard = UPSGuard()
        guard.observe(50, 10)
        result = guard.observe(400, 9)
        self.assertEqual(result.state, "unknown")

    def test_short_sample_window_is_ignored(self):
        guard = UPSGuard()
        guard.observe(0, 0.0)
        self.assertEqual(guard.observe(60, 1.0).state, "unknown")

    def test_save_switch_resets_health(self):
        guard = UPSGuard()
        for i in range(4):
            guard.observe(1000 + i * 300, i * 5.0)
        self.assertEqual(guard.state, "healthy")
        self.assertEqual(guard.observe(0, 25).state, "unknown")
        self.assertFalse(guard.budget().ai_allowed)

    def test_explicit_disconnect_resets(self):
        guard = UPSGuard()
        for i in range(4):
            guard.observe(i * 300, i * 5)
        guard.reset()
        self.assertFalse(guard.budget().ai_allowed)
        self.assertIsNone(guard.budget().estimated_ups)

    def test_bad_samples_rejected(self):
        guard = UPSGuard()
        for tick, at in ((True, 1), (-1, 1), (1.5, 1), (1, float("nan"))):
            with self.subTest(tick=tick, at=at), self.assertRaises(ValueError):
                guard.observe(cast(int, tick), at)

    def test_time_warp_restarts_sampling(self):
        guard = UPSGuard()
        guard.observe(0, 0)
        self.assertEqual(guard.observe(2000, 5).state, "unknown")

    def test_ordinary_background_does_not_change_game_priority(self):
        normal = 0x08000000
        below = 0x00004000
        self.assertEqual(
            owned_process_creationflags("llama", windows=True,
                                        no_window=normal, below_normal=below),
            normal | below,
        )
        for name in ("host", "server", "client", "dashboard"):
            self.assertEqual(
                owned_process_creationflags(name, windows=True,
                                            no_window=normal, below_normal=below),
                normal,
            )
        self.assertEqual(owned_process_creationflags("llama", windows=False), 0)


if __name__ == "__main__":
    unittest.main()
