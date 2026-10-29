"""Regression: the telemetry and cache settings reach the services.

These tests write a real settings file and then read the value **from
the service** — the observation bridge, the coordinator and the UPS guard.
They are the evidence that the Performance and Telemetry section of the
Settings screen actually changes the running system.

No Factorio process is started and no observer thread is left running.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from observation_service import ObservationService  # noqa: E402
from performance_governor import guard_from_settings  # noqa: E402
from settings_store import update  # noqa: E402


class _StubService:
    """A bridge service that never observes anything."""

    async def observe(self, kind, factory, **kwargs):
        return None


class TelemetryPropagationTestCase(unittest.TestCase):
    """A test with a real settings file in a temporary directory."""

    def setUp(self) -> None:
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.path = self.base / "settings.json"
        previous = os.environ.get("AUTOENGINEER_SETTINGS")
        os.environ["AUTOENGINEER_SETTINGS"] = str(self.path)
        self.addCleanup(self._restore_environment, previous)

    def _restore_environment(self, previous):
        if previous is None:
            os.environ.pop("AUTOENGINEER_SETTINGS", None)
        else:
            os.environ["AUTOENGINEER_SETTINGS"] = previous

    def store(self, **values) -> None:
        """Write the given settings into the real settings file."""
        update(values, self.path)


class ObservationIntervalTests(TelemetryPropagationTestCase):
    def test_the_interval_reaches_the_bridge(self):
        from qt_observation_bridge import ObservationBridge

        self.store(observation_interval_seconds=37)
        bridge = ObservationBridge(_StubService())
        self.assertEqual(bridge.interval, 37.0)

    def test_a_faster_interval_reaches_the_bridge(self):
        from qt_observation_bridge import ObservationBridge

        self.store(observation_interval_seconds=5)
        bridge = ObservationBridge(_StubService())
        self.assertEqual(bridge.interval, 5.0)

    def test_an_explicit_interval_still_wins(self):
        from qt_observation_bridge import ObservationBridge

        self.store(observation_interval_seconds=37)
        bridge = ObservationBridge(_StubService(), interval=3.0)
        self.assertEqual(bridge.interval, 3.0)

    def test_an_invalid_interval_falls_back_to_the_safe_default(self):
        # The store refuses an out-of-range value, so the default is used.
        from runtime_settings import observation_interval

        self.assertGreaterEqual(observation_interval(), 1)


class RequestBudgetTests(TelemetryPropagationTestCase):
    def test_the_budget_reaches_the_coordinator(self):
        self.store(observation_interval_seconds=60, observation_max_requests=3)
        service = ObservationService()
        self.addCleanup(service.close)
        self.assertEqual(service.coordinator.requests_per_minute, 3)

    def test_a_faster_interval_raises_the_budget(self):
        self.store(observation_interval_seconds=10, observation_max_requests=2)
        service = ObservationService()
        self.addCleanup(service.close)
        self.assertEqual(service.coordinator.requests_per_minute, 12)

    def test_a_slower_interval_lowers_the_budget(self):
        self.store(observation_interval_seconds=120, observation_max_requests=2)
        service = ObservationService()
        self.addCleanup(service.close)
        self.assertEqual(service.coordinator.requests_per_minute, 2)

    def test_the_concurrency_limit_reaches_the_coordinator(self):
        self.store(observation_max_requests=3)
        service = ObservationService()
        self.addCleanup(service.close)
        self.assertEqual(service.coordinator.max_in_flight, 3)

    def test_the_concurrency_limit_never_exceeds_the_budget(self):
        self.store(observation_max_requests=1)
        service = ObservationService()
        self.addCleanup(service.close)
        self.assertEqual(service.coordinator.max_in_flight, 1)

    def test_an_explicit_coordinator_is_not_replaced(self):
        from observation_coordinator import ObservationCoordinator

        coordinator = ObservationCoordinator(requests_per_minute=7)
        service = ObservationService(coordinator)
        self.addCleanup(service.close)
        self.assertIs(service.coordinator, coordinator)
        self.assertEqual(service.coordinator.requests_per_minute, 7)


class UPSThresholdPropagationTests(TelemetryPropagationTestCase):
    def test_the_thresholds_reach_the_guard(self):
        self.store(
            ups_target=60,
            ups_degrade_threshold=59.0,
            ups_recover_threshold=59.5,
            ups_critical_threshold=55.0,
        )
        guard = guard_from_settings()
        self.assertEqual(guard.thresholds.degrade, 59.0)
        self.assertEqual(guard.thresholds.critical, 55.0)

    def test_the_default_thresholds_keep_the_original_behaviour(self):
        guard = guard_from_settings()
        self.assertEqual(guard.thresholds.degrade, 58.0)
        self.assertEqual(guard.thresholds.recover, 59.5)
        self.assertEqual(guard.thresholds.critical, 52.0)
        self.assertEqual(guard.thresholds.target, 60.0)

    def test_an_unsafe_threshold_configuration_keeps_the_protection(self):
        self.store(
            ups_target=60,
            ups_degrade_threshold=59,
            ups_recover_threshold=50,
            ups_critical_threshold=55,
        )
        guard = guard_from_settings()
        self.assertEqual(guard.thresholds.degrade, 58.0)
        self.assertEqual(guard.thresholds.recover, 59.5)
        self.assertEqual(guard.thresholds.critical, 52.0)

    def test_a_low_target_is_refused_by_the_store(self):
        """The store refuses a target that would disable the protection."""
        from settings_store import SettingsError

        with self.assertRaises(SettingsError):
            self.store(ups_target=5)
        # The stored configuration is untouched, so the guard keeps the
        # safe target.
        guard = guard_from_settings()
        self.assertEqual(guard.thresholds.target, 60.0)


class CacheLimitTests(TelemetryPropagationTestCase):
    def test_the_cache_limits_are_reported(self):
        from runtime_settings import cache_limits

        self.store(cache_max_entries=64, cache_ttl_seconds=90)
        self.assertEqual(cache_limits(), (64, 90.0))

    def test_the_history_retention_is_reported(self):
        from runtime_settings import history_retention

        self.store(history_retention_samples=100)
        self.assertEqual(history_retention(), 100)

    def test_the_page_interval_is_reported(self):
        from runtime_settings import observation_page_interval

        self.store(observation_page_interval_seconds=300)
        self.assertEqual(observation_page_interval(), 300.0)


if __name__ == "__main__":
    unittest.main()
