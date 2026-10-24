"""Tests for standalone read-only dashboard status model."""
import unittest
from typing import Any, cast

from agent.dashboard_rebuild_state import Availability, dashboard_state


class DashboardRebuildStateTests(unittest.TestCase):
    def test_disconnected_never_displays_ready(self):
        state = dashboard_state({"inventory": [], "telemetry": {"production": {}, "power": {}}})
        self.assertEqual(state.connection.availability, Availability.DISCONNECTED)
        self.assertEqual(state.production.availability, Availability.DISCONNECTED)

    def test_connected_without_data_is_unavailable(self):
        state = dashboard_state({}, connected=True)
        self.assertEqual(state.connection.availability, Availability.READY)
        self.assertEqual(state.power.availability, Availability.UNAVAILABLE)

    def test_real_empty_inventory_is_available(self):
        state = dashboard_state({"inventory": []}, connected=True)
        self.assertEqual(state.inventory.availability, Availability.READY)

    def test_panel_empty_mapping_is_valid_observation(self):
        state = dashboard_state({"telemetry": {"power": {}}}, connected=True)
        self.assertEqual(state.power.availability, Availability.READY)
        self.assertEqual(state.power.source, "live observer")

    def test_partial_and_stale_statuses(self):
        state = dashboard_state({"telemetry": {"production": {"partial": True}}}, connected=True)
        self.assertEqual(state.production.availability, Availability.PARTIAL)
        stale = dashboard_state({"telemetry": {"power": {}}}, connected=True, stale=True)
        self.assertEqual(stale.power.availability, Availability.STALE)

    def test_invalid_input_is_not_invented(self):
        state = dashboard_state(cast(Any, "not an observation"), connected=True)
        self.assertEqual(state.research.availability, Availability.UNAVAILABLE)

    def test_supported_target_is_explicit(self):
        self.assertEqual(dashboard_state(None).game_version, "2.1.23")


if __name__ == "__main__":
    unittest.main()
