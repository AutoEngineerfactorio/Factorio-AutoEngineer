"""Tests for the configurable UPS thresholds.

The thresholds are safety-critical: a wrong value could disable the
protection that keeps the game at a stable update rate. These tests
therefore check that an **unsafe configuration is refused** and that the
protective defaults are used instead.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from performance_governor import (  # noqa: E402
    CRITICAL_UPS,
    DEGRADE_UPS,
    RECOVER_UPS,
    UPSGuard,
    UPSThresholds,
    guard_from_settings,
)


def settings(**values):
    """Return a settings-like mapping with the given overrides."""
    base = {
        "ups_target": 60,
        "ups_degrade_threshold": 58,
        "ups_recover_threshold": 59,
        "ups_critical_threshold": 52,
    }
    base.update(values)
    return base


class ThresholdValidationTests(unittest.TestCase):
    def test_the_defaults_are_accepted(self):
        thresholds = UPSThresholds.validated(
            60.0, DEGRADE_UPS, RECOVER_UPS, CRITICAL_UPS)
        self.assertEqual(thresholds.target, 60.0)
        self.assertEqual(thresholds.degrade, DEGRADE_UPS)

    def test_a_healthy_configuration_is_kept(self):
        thresholds = UPSThresholds.validated(60.0, 55.0, 58.0, 50.0)
        self.assertEqual(thresholds.degrade, 55.0)
        self.assertEqual(thresholds.recover, 58.0)
        self.assertEqual(thresholds.critical, 50.0)

    def test_an_unordered_configuration_is_refused(self):
        thresholds = UPSThresholds.validated(60.0, 58.0, 55.0, 52.0)
        self.assertEqual(thresholds.degrade, DEGRADE_UPS)

    def test_a_recover_above_the_target_is_refused(self):
        thresholds = UPSThresholds.validated(60.0, 55.0, 61.0, 50.0)
        self.assertEqual(thresholds.recover, RECOVER_UPS)

    def test_a_target_below_the_minimum_is_refused(self):
        thresholds = UPSThresholds.validated(10.0, 8.0, 9.0, 5.0)
        self.assertEqual(thresholds.target, 60.0)

    def test_a_band_that_is_too_narrow_is_refused(self):
        thresholds = UPSThresholds.validated(60.0, 58.0, 58.1, 52.0)
        self.assertEqual(thresholds.recover, RECOVER_UPS)

    def test_a_non_finite_value_is_refused(self):
        thresholds = UPSThresholds.validated(
            60.0, float("nan"), 59.0, 52.0)
        self.assertEqual(thresholds.degrade, DEGRADE_UPS)

    def test_a_non_numeric_value_is_refused(self):
        thresholds = UPSThresholds.validated(60.0, "fast", 59.0, 52.0)
        self.assertEqual(thresholds.degrade, DEGRADE_UPS)

    def test_a_critical_above_the_degrade_is_refused(self):
        thresholds = UPSThresholds.validated(60.0, 55.0, 58.0, 56.0)
        self.assertEqual(thresholds.critical, CRITICAL_UPS)


class ThresholdFromSettingsTests(unittest.TestCase):
    def test_the_settings_are_used_when_they_are_safe(self):
        thresholds = UPSThresholds.from_settings(
            settings(ups_degrade_threshold=55, ups_recover_threshold=58,
                     ups_critical_threshold=50))
        self.assertEqual(thresholds.degrade, 55.0)

    def test_an_unsafe_setting_falls_back_to_the_defaults(self):
        thresholds = UPSThresholds.from_settings(
            settings(ups_degrade_threshold=58, ups_recover_threshold=55))
        self.assertEqual(thresholds.degrade, DEGRADE_UPS)
        self.assertEqual(thresholds.recover, RECOVER_UPS)

    def test_a_broken_settings_object_falls_back_to_the_defaults(self):
        thresholds = UPSThresholds.from_settings(object())
        self.assertEqual(thresholds.degrade, DEGRADE_UPS)

    def test_a_none_settings_falls_back_to_the_defaults(self):
        thresholds = UPSThresholds.from_settings(None)
        self.assertEqual(thresholds.degrade, DEGRADE_UPS)


class GuardUsesThresholdsTests(unittest.TestCase):
    def _rate(self, guard, ups, samples=4):
        """Feed the guard a steady tick rate and return its final state.

        The tick rate is produced by advancing the tick counter by
        ``ups`` every ten seconds, which is a real sample of the wanted
        rate rather than a fixed one.
        """
        tick = 0
        for index in range(samples):
            tick += int(ups * 10)
            guard.observe(tick, float(index) * 10.0)
        return guard.state

    def test_a_raised_threshold_degrades_earlier(self):
        # A *raised* degrade level makes the guard reduce the background
        # work sooner: 59 UPS is still healthy for the default guard but
        # already below the raised degrade level of 59.5.
        thresholds = UPSThresholds.validated(60.0, 59.5, 60.0, 55.0)
        guard = UPSGuard(thresholds=thresholds)
        self.assertEqual(self._rate(guard, 59.0), "degraded")
        default_guard = UPSGuard()
        self.assertNotEqual(self._rate(default_guard, 59.0), "degraded")

    def test_a_lowered_threshold_degrades_later(self):
        # A *lowered* degrade level is the opposite: the guard keeps
        # working at a rate where the default one would already have
        # paused the optional work. 53 UPS is below the default degrade
        # level of 58 but above the lowered level of 50.
        thresholds = UPSThresholds.validated(60.0, 50.0, 52.0, 45.0)
        guard = UPSGuard(thresholds=thresholds)
        self.assertNotEqual(self._rate(guard, 53.0), "degraded")
        default_guard = UPSGuard()
        self.assertEqual(self._rate(default_guard, 53.0), "degraded")

    def test_the_default_guard_is_unchanged(self):
        guard = UPSGuard()
        self.assertEqual(guard.thresholds.degrade, DEGRADE_UPS)
        self.assertEqual(guard.thresholds.recover, RECOVER_UPS)
        self.assertEqual(guard.thresholds.critical, CRITICAL_UPS)
        self.assertEqual(guard.thresholds.target, 60.0)

    def test_a_critical_threshold_stops_the_ai_immediately(self):
        # A raised critical level of 57 with the ordered set
        # 53 < 57 < 58 < 60. At 56 UPS the guard must go critical at once
        # instead of waiting for the hysteresis.
        thresholds = UPSThresholds.validated(60.0, 58.0, 59.5, 57.0)
        guard = UPSGuard(thresholds=thresholds)
        guard.observe(0, 0.0)
        guard.observe(560, 10.0)
        budget = guard.budget()
        self.assertEqual(budget.state, "critical")
        self.assertFalse(budget.ai_allowed)

    def test_a_guard_from_settings_uses_the_configured_thresholds(self):
        guard = guard_from_settings(
            settings(ups_degrade_threshold=55, ups_recover_threshold=58,
                     ups_critical_threshold=50))
        self.assertEqual(guard.thresholds.degrade, 55.0)

    def test_a_guard_from_unsafe_settings_keeps_the_protection(self):
        guard = guard_from_settings(
            settings(ups_degrade_threshold=1, ups_recover_threshold=2,
                     ups_critical_threshold=3))
        self.assertEqual(guard.thresholds.degrade, DEGRADE_UPS)
        self.assertEqual(guard.thresholds.critical, CRITICAL_UPS)


if __name__ == "__main__":
    unittest.main()
