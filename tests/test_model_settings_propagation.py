"""Regression: a stored setting reaches the service that consumes it.

These tests write a real settings file and then read the value **from
the service**, not from the bridge. They are the evidence that a control
in the Settings screen actually changes the running system.

No Factorio process is started and no model server is started.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from observation_service import ObservationService  # noqa: E402
from performance_governor import guard_from_settings  # noqa: E402
from settings_store import load, update  # noqa: E402


class PropagationTestCase(unittest.TestCase):
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


class ModelEndpointPropagationTests(PropagationTestCase):
    def test_the_stored_endpoint_reaches_the_configuration(self):
        self.store(llm_endpoint="http://127.0.0.1:9411/v1")
        from autoengineer_config import get_settings

        self.assertEqual(get_settings()["llm_api_url"], "http://127.0.0.1:9411/v1")

    def test_the_stored_model_reaches_the_configuration(self):
        self.store(llm_model="FrogNano-1B")
        from autoengineer_config import get_settings

        self.assertEqual(get_settings()["llm_model"], "FrogNano-1B")

    def test_a_remote_endpoint_is_never_applied(self):
        from settings_store import SettingsError

        # The store refuses a remote endpoint outright, so it can never
        # reach the configuration.
        with self.assertRaises(SettingsError):
            self.store(llm_endpoint="https://api.example.com/v1")
        from autoengineer_config import get_settings

        self.assertNotEqual(
            get_settings()["llm_api_url"], "https://api.example.com/v1")

    def test_the_inference_services_read_the_endpoint_at_call_time(self):
        """The endpoint must not be frozen when the module is imported."""
        import ai_movement
        import live_planner

        self.store(llm_endpoint="http://127.0.0.1:9422/v1")
        self.assertEqual(ai_movement.api_base(), "http://127.0.0.1:9422/v1")
        self.assertEqual(live_planner.api_base(), "http://127.0.0.1:9422/v1")

        self.store(llm_endpoint="http://127.0.0.1:9433/v1")
        self.assertEqual(ai_movement.api_base(), "http://127.0.0.1:9433/v1")
        self.assertEqual(live_planner.api_base(), "http://127.0.0.1:9433/v1")

    def test_the_supervised_agent_reads_the_endpoint_at_call_time(self):
        import supervised_agent

        self.store(llm_endpoint="http://127.0.0.1:9444/v1")
        self.assertEqual(
            supervised_agent.api_base(), "http://127.0.0.1:9444/v1")


class TelemetryPropagationTests(PropagationTestCase):
    def test_the_observation_interval_reaches_the_bridge(self):
        from qt_observation_bridge import ObservationBridge

        class _Service:
            async def observe(self, kind, factory, **kwargs):
                return None

        self.store(observation_interval_seconds=37)
        bridge = ObservationBridge(_Service())
        self.assertEqual(bridge.interval, 37.0)

    def test_an_explicit_interval_still_wins(self):
        from qt_observation_bridge import ObservationBridge

        class _Service:
            async def observe(self, kind, factory, **kwargs):
                return None

        self.store(observation_interval_seconds=37)
        bridge = ObservationBridge(_Service(), interval=3.0)
        self.assertEqual(bridge.interval, 3.0)

    def test_the_request_budget_reaches_the_coordinator(self):
        self.store(observation_interval_seconds=60, observation_max_requests=3)
        service = ObservationService()
        self.addCleanup(service.close)
        # One round per minute at a 60 second interval, three requests a
        # round: the coordinator must allow three requests a minute.
        self.assertEqual(service.coordinator.requests_per_minute, 3)

    def test_a_faster_interval_raises_the_budget(self):
        self.store(observation_interval_seconds=10, observation_max_requests=2)
        service = ObservationService()
        self.addCleanup(service.close)
        self.assertEqual(service.coordinator.requests_per_minute, 12)

    def test_the_concurrency_limit_reaches_the_coordinator(self):
        self.store(observation_max_requests=3)
        service = ObservationService()
        self.addCleanup(service.close)
        self.assertEqual(service.coordinator.max_in_flight, 3)


class UPSPropagationTests(PropagationTestCase):
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
        """A default installation must behave exactly as it did before."""
        guard = guard_from_settings()
        self.assertEqual(guard.thresholds.degrade, 58.0)
        self.assertEqual(guard.thresholds.recover, 59.5)
        self.assertEqual(guard.thresholds.critical, 52.0)

    def test_an_unsafe_threshold_configuration_keeps_the_protection(self):
        self.store(
            ups_target=60,
            ups_degrade_threshold=59,
            ups_recover_threshold=50,
            ups_critical_threshold=55,
        )
        guard = guard_from_settings()
        # The ordered, protective defaults are used, so the guard never
        # loses its protection because of a wrong setting.
        self.assertEqual(guard.thresholds.degrade, 58.0)
        self.assertEqual(guard.thresholds.recover, 59.5)


class SettingsFileTests(PropagationTestCase):
    def test_the_stored_file_is_the_one_the_services_read(self):
        self.store(llm_model="from-file")
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["settings"]["llm_model"], "from-file")
        self.assertEqual(load(self.path).get("llm_model"), "from-file")

    def test_a_broken_settings_file_does_not_break_the_services(self):
        self.path.write_text("not json", encoding="utf-8")
        from runtime_settings import model_endpoint

        # The service keeps working with the safe default.
        self.assertTrue(model_endpoint().startswith("http://"))


class OverlaySecurityTests(PropagationTestCase):
    """The overlay must never hide an invalid base configuration."""

    def setUp(self) -> None:
        super().setUp()
        from unittest.mock import patch

        self.config_root = self.base / "config"
        self.config_root.mkdir()
        self._project_root = patch(
            "autoengineer_config.PROJECT_ROOT", self.config_root)
        self._project_root.start()
        self.addCleanup(self._project_root.stop)
        self._environment = patch.dict(
            os.environ,
            {"AUTOENGINEER_CONFIG": str(self.config_root / "config.local.json")})
        self._environment.start()
        self.addCleanup(self._environment.stop)

    def _write_base(self, document: str) -> None:
        (self.config_root / "config.local.json").write_text(
            document, encoding="utf-8")

    def test_a_credential_in_the_base_url_is_still_refused(self):
        from autoengineer_config import get_settings

        self._write_base(
            '{"llm_api_url":"http://user:secret-value@localhost/v1"}')
        with self.assertRaises(ValueError) as caught:
            get_settings()
        self.assertNotIn("secret-value", str(caught.exception))

    def test_a_remote_base_endpoint_is_still_refused(self):
        from autoengineer_config import get_settings

        self._write_base('{"llm_api_url":"https://example.com/v1"}')
        with self.assertRaises(ValueError):
            get_settings()

    def test_a_valid_base_endpoint_is_replaced_by_the_settings(self):
        from autoengineer_config import get_settings

        self._write_base('{"llm_api_url":"http://127.0.0.1:9500/v1"}')
        self.store(llm_endpoint="http://127.0.0.1:9600/v1")
        self.assertEqual(get_settings()["llm_api_url"], "http://127.0.0.1:9600/v1")


if __name__ == "__main__":
    unittest.main()
