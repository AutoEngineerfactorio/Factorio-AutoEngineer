"""Tests for the approved industrial command center, without a game process."""
import os
import sys
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    QApplication = import_module("PySide6.QtWidgets").QApplication
    QPushButton = import_module("PySide6.QtWidgets").QPushButton
    from qt_shell import ShellWindow
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 unavailable")
class CommandCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = ShellWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def test_unobserved_world_is_unknown(self):
        home = self.window.command_center()
        self.assertEqual(home.quick_version.text(), "—")
        self.assertEqual(home.world_fields["UPS"].text(), "—")
        self.assertIn("OFFLINE", home.live.text())

    def test_verified_frame_feeds_world_and_telemetry(self):
        self.window.apply_frame({
            "schema": 1, "live": True, "profile": "vanilla",
            "gameVersion": "2.1.23", "ups": 60.0,
        })
        home = self.window.command_center()
        self.assertEqual(home.quick_version.text(), "2.1.23")
        self.assertEqual(home.quick_profile.text(), "vanilla")
        self.assertIn("60", home.metric_fields["UPS"].text())
        self.assertIn("LIVE", home.live.text())
        self.assertEqual(home.metric_fields["Power"].text(), "—  ·  unavailable")

    def test_human_navigation_uses_the_existing_workspace(self):
        home = self.window.command_center()
        buttons = home.findChildren(QPushButton)
        target = next(b for b in buttons if b.text() == "Open Blueprint Library")
        target.click()
        self.assertEqual(self.window.current_workspace, "Blueprint Studio")

    def test_unverified_start_and_stop_controls_are_locked(self):
        home = self.window.command_center()
        buttons = home.findChildren(QPushButton)
        start = next(b for b in buttons if b.text().startswith("Start AI"))
        stop = next(b for b in buttons if b.text().startswith("Stop AI"))
        full = next(b for b in buttons if b.text().startswith("Full Autonomous"))
        self.assertFalse(start.isEnabled())
        self.assertFalse(stop.isEnabled())
        self.assertFalse(full.isEnabled())

    def test_disconnect_erases_metrics_without_lying(self):
        self.window.apply_frame({
            "schema": 1, "live": True, "ups": 60,
        })
        self.window.apply_disconnect("lost")
        home = self.window.command_center()
        self.assertIn("DISCONNECTED", home.live.text())
        self.assertEqual(home.world_fields["UPS"].text(), "—")
        self.assertEqual(home.metric_fields["Power"].text(), "—")

    def test_telemetry_cards_reuse_validated_model(self):
        from qt_telemetry import FlowRow, PowerRow, TelemetryModel

        model = TelemetryModel(
            status="ok", production_status="ok", power_status="ok",
            flows=[FlowRow("iron-plate", "item", 0, 120, 0, 2)],
            networks=[PowerRow(1, 250000, 125000, 1, 1, 0, 0)],
        )
        home = self.window.command_center()
        home.set_telemetry_model(model, age_seconds=3)
        self.assertIn("2.0 items/s", home.metric_fields["Production"].text())
        self.assertIn("125.00 kW", home.metric_fields["Power"].text())
        self.window.apply_frame({"schema": 1})
        self.assertIn("2.0 items/s", home.metric_fields["Production"].text())
        self.window.apply_disconnect("lost")
        self.assertEqual(home.metric_fields["Production"].text(), "—")


    def test_missing_telemetry_clears_previous_network_readings(self):
        from qt_telemetry import PowerRow, TelemetryModel

        home = self.window.command_center()
        home.set_telemetry_model(TelemetryModel(
            status="ok", power_status="ok",
            networks=[PowerRow(1, 250000, 125000, 1, 1, 0, 0)]))
        self.assertIn("250.00 kW", home.metric_fields["Power Generation"].text())
        home.set_telemetry_model(TelemetryModel(status="unavailable"))
        self.assertEqual(home.metric_fields["Power Generation"].text(), "—")
        self.assertEqual(home.metric_fields["Power"].text(), "—")

    def test_header_toolbar_navigates_to_existing_settings(self):
        self.window.header.tools["Settings"].click()
        self.assertEqual(self.window.current_workspace, "Settings")
        self.assertFalse(self.window.header.tools["Notifications"].isEnabled())


    def test_research_and_local_pollution_render_real_context(self):
        from qt_telemetry import TelemetryModel

        home = self.window.command_center()
        home.set_telemetry_model(TelemetryModel(status="ok", research_active=True,
            research_name="mining", research_progress=.5, pollution_amount=12.5, partial=True))
        self.assertIn("50%", home.metric_fields["Research"].text())
        self.assertIn("12.5", home.metric_fields["Pollution"].text())
        self.assertIn("local chunk", home.metric_fields["Pollution"].text())
        self.assertNotIn("partial", home.metric_fields["Research"].text())
        self.window.apply_disconnect("lost")
        self.assertEqual(home.metric_fields["Research"].text(), "—")


    def test_inventory_bridge_frame_updates_dashboard_and_logistics(self):
        from qt_observation_bridge import UiFrame
        from test_qt_inventory_observations import frame

        self.window.apply_ui_frame(UiFrame(kind="inventory", value=frame(), state="observed"))
        home = self.window.command_center()
        self.assertIn("120 / 200 bots", home.metric_fields["Logistics"].text())
        observed = self.window.inventory_widget("Logistics").snapshot
        assert observed is not None
        self.assertEqual(observed.robots.available_logistic_robots, 120)
        self.window.apply_disconnect("lost")
        self.assertEqual(home.metric_fields["Logistics"].text(), "—")


    def test_tick_rate_is_displayed_as_estimated_not_observed_ups(self):
        from qt_observation_bridge import UiFrame

        self.window.apply_ui_frame(UiFrame(kind="status", value={"tick": 240},
            state="observed", derived_ups=60.0, age_seconds=0))
        shown = self.window.command_center().world_fields["UPS"].text()
        self.assertIn("60", shown)
        self.assertIn("estimated", shown)

    def test_changed_surface_invalidates_chain_and_blueprint_planning(self):
        from dataclasses import replace

        from qt_observation_bridge import UiFrame
        from test_qt_recipe_planner import snapshot

        self.window.recipe_widget().set_snapshot(replace(snapshot(), surface="nauvis"))
        self.window.apply_ui_frame(UiFrame(kind="status", value={"surface": "different"},
                                           state="observed"))
        self.assertFalse(self.window.recipe_widget().chain.calculate_button.isEnabled())


    def test_fresh_bridge_observation_is_live_and_disconnect_clears_header(self):
        from qt_observation_bridge import UiFrame

        self.window.apply_ui_frame(UiFrame(kind="status", value={"status": "ok", "tick": 1},
                                           state="observed"))
        self.assertIn("LIVE", self.window.header.connection.text())
        self.window.apply_disconnect("Disconnected")
        self.assertIn("UNAVAILABLE", self.window.header.connection.text())
        self.window.refresh_metrics()
        self.assertNotIn("LIVE", self.window.header.connection.text())


    def test_power_cards_report_delivered_power_not_maximum_capacity(self):
        from qt_telemetry import PowerRow, TelemetryModel

        home = self.window.command_center()
        home.set_telemetry_model(TelemetryModel(status="ok", power_status="ok",
            networks=[PowerRow(1, 1000000, 800000, .5, .4, 0, 0)]))
        self.assertIn("400.00 kW", home.metric_fields["Power"].text())
        self.assertIn("400.00 kW", home.metric_fields["Power Generation"].text())


    def test_surface_change_requests_one_new_catalog_and_blocks_old_results(self):
        from dataclasses import replace
        from unittest.mock import patch

        from qt_observation_bridge import UiFrame
        from test_qt_recipe_planner import snapshot

        self.window.recipe_widget().set_snapshot(replace(snapshot(), surface="nauvis"))
        with patch.object(self.window, "request_catalog_refresh", return_value=True) as refresh:
            for tick in (2, 3):
                self.window.apply_ui_frame(UiFrame(kind="status", state="observed",
                    value={"status": "ok", "tick": tick, "surface": "other"}))
            refresh.assert_called_once()
        self.assertFalse(self.window.recipe_widget().chain.calculate_button.isEnabled())


    def test_surface_change_during_partial_catalog_refresh_requests_new_epoch(self):
        from dataclasses import replace
        from unittest.mock import patch

        from qt_observation_bridge import UiFrame
        from test_qt_recipe_planner import snapshot

        partial = replace(snapshot(), surface="nauvis", status="ok", total_count=2, total_pages=2)
        self.window.recipe_widget().set_snapshot(partial)
        with patch.object(self.window, "request_catalog_refresh", return_value=True) as refresh:
            self.window.apply_ui_frame(UiFrame(kind="status", state="observed",
                value={"status": "ok", "surface": "new-surface"}))
            refresh.assert_called_once()

    def test_status_failure_disables_planning_until_a_fresh_catalog_arrives(self):
        from unittest.mock import patch

        from qt_observation_bridge import UiFrame
        from test_qt_recipe_planner import snapshot

        self.window.recipe_widget().set_snapshot(snapshot())
        self.window.apply_ui_frame(UiFrame(kind="status", state="unavailable", detail="Backend unavailable"))
        self.assertFalse(self.window.recipe_widget().chain.calculate_button.isEnabled())
        self.assertNotIn("LIVE", self.window.header.connection.text())
        with patch.object(self.window, "request_catalog_refresh", return_value=True) as refresh:
            for tick in (1, 2):
                self.window.apply_ui_frame(UiFrame(kind="status", state="observed",
                    value={"status": "ok", "tick": tick}))
            refresh.assert_called_once()
        self.assertFalse(self.window.recipe_widget().chain.calculate_button.isEnabled())
