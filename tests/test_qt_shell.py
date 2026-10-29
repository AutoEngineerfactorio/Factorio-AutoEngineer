"""Regression tests for the Qt shell window.

These tests need PySide6. They run on the **offscreen** platform plugin so
they need no display server, and they skip cleanly when PySide6 is not
installed, so the offline suite still passes in an environment without the
optional UI dependency.
"""

import os
import sys
import unittest
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    # PySide6 is imported dynamically so a static analyzer does not need it
    # installed to inspect this file. The same pattern is used in
    # ``agent/qt_shell.py`` and ``agent/qt_dashboard.py``.
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication
    QLabel = import_module("PySide6.QtWidgets").QLabel

    import qt_shell
    from qt_observation_bridge import UiFrame

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class ShellWindowTests(unittest.TestCase):
    """The shell builds, navigates and never fabricates a number."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = qt_shell.ShellWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def test_the_window_builds_with_every_workspace(self):
        for name in qt_shell.WORKSPACES:
            self.assertIn(name, self.window._pages)

    def test_the_first_workspace_is_shown_initially(self):
        self.assertEqual(self.window.current_workspace, qt_shell.WORKSPACES[0])

    def test_navigation_switches_the_visible_workspace(self):
        self.window.show_workspace("Production")
        self.assertEqual(self.window.current_workspace, "Production")

    def test_navigation_checks_exactly_one_rail_button(self):
        self.window.show_workspace("Diagnostics")
        checked = [name for name, button in self.window.rail.buttons.items()
                   if button.isChecked()]
        self.assertEqual(checked, ["Diagnostics"])

    def test_an_unknown_workspace_is_rejected(self):
        with self.assertRaises(KeyError):
            self.window.show_workspace("No Such Workspace")

    def test_the_page_of_a_workspace_is_reachable(self):
        page = self.window.page("Production")
        self.assertIsNotNone(page)
        with self.assertRaises(KeyError):
            self.window.page("No Such Workspace")

    def test_a_direct_header_state_is_applied(self):
        from qt_theme import build_header_state

        state = build_header_state({"status": "unavailable"})
        self.window.apply_header_state(state)
        self.assertIn("UNAVAILABLE", self.window.header.connection.text())

    def test_a_named_observation_updates_one_metric(self):
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.assertEqual(self.window.header.tiles["UPS"].value.text(), "60.00")

    def test_the_factory_map_workspace_hosts_the_map_widget(self):
        from qt_map_widget import MapWidget

        self.assertIsInstance(self.window.map_widget(), MapWidget)

    def test_the_telemetry_workspaces_host_the_telemetry_widget(self):
        from qt_telemetry_widget import TelemetryWidget

        self.assertIsInstance(
            self.window.telemetry_widget("Production"), TelemetryWidget)
        self.assertIsInstance(
            self.window.telemetry_widget("Electrical"), TelemetryWidget)

    def test_the_recipe_workspace_hosts_the_observed_catalog_widget(self):
        from qt_catalog_widget import CatalogWidget

        self.assertIsInstance(self.window.catalog_widget(), CatalogWidget)

    def test_an_observed_catalog_reaches_the_recipe_workspace(self):
        frame = {
            "catalog_status": {
                "status": "assembled", "page": 1, "page_size": 32,
                "total_count": 1, "total_pages": 1,
            },
            "capabilities": {
                "game_version": "2.1.23", "force": "player",
                "surface": "nauvis", "tick": 42, "truncated": False,
                "source_fingerprint": "catalog-v1:abc",
                "research": ["automation"],
                "recipes": [{
                    "name": "iron-gear-wheel", "enabled": True,
                    "hidden": False, "category": "crafting",
                    "categories": ["crafting"], "crafting_time": 0.5,
                    "ingredients": [], "products": [],
                }],
                "machines": [],
            },
        }
        self.window.set_catalog(frame)
        widget = self.window.catalog_widget()
        self.assertEqual(widget.recipe_table.rowCount(), 1)
        self.assertEqual(
            widget.recipe_table.item(0, 0).text(), "iron-gear-wheel")

    def test_an_observed_map_reaches_the_map_widget(self):
        self.window.set_map(
            {"origins": [(0, 0)],
             "entities": [{"kind": "enemy", "x": 10, "y": 10}],
             "terrain": {}, "overlays": {}},
            player={"x": 5, "y": 5})
        scene = self.window.map_widget().scene
        assert scene is not None
        self.assertTrue(scene.primitives)

    def test_an_observed_telemetry_reaches_both_telemetry_workspaces(self):
        payload = {
            "schema": 1,
            "tick": 5,
            "production": {
                "status": "unavailable",
                "reason": "No flow statistics",
                "items": {"status": "unavailable", "reason": "none"},
                "fluids": {"status": "unavailable", "reason": "none"},
            },
            "power": {
                "status": "unavailable",
                "reason": "No power telemetry",
                "unit": "joules_per_tick",
                "tick": 5,
                "networks": [],
                "partial": False,
            },
        }
        self.window.set_telemetry(payload)
        for workspace in ("Production", "Electrical"):
            widget = self.window.telemetry_widget(workspace)
            self.assertIn("unavailable", widget.status.text())
            self.assertIn("tick 5", widget.status.text())

    def test_no_telemetry_shows_no_rows(self):
        """A missing observation must not become a table of zeroes."""
        widget = self.window.telemetry_widget("Production")
        self.assertEqual(widget.flow_table.rowCount(), 0)
        self.assertEqual(widget.power_table.rowCount(), 0)

    def test_clicking_a_rail_button_switches_the_workspace(self):
        button = self.window.rail.button("Electrical")
        button.click()
        self.assertEqual(self.window.current_workspace, "Electrical")

    def test_the_header_shows_the_offline_state_without_a_frame(self):
        self.assertIn("OFFLINE", self.window.header.connection.text())
        self.assertIn("READ ONLY", self.window.header.mode.text())

    def test_a_snapshot_frame_is_not_reported_as_live(self):
        self.window.apply_frame({"schema": 1, "status": "ok"})
        self.assertNotIn("LIVE", self.window.header.connection.text())

    def test_an_unavailable_frame_is_reported_as_unavailable(self):
        self.window.apply_frame({"status": "unavailable"})
        self.assertIn("UNAVAILABLE", self.window.header.connection.text())

    def test_a_live_frame_needs_an_explicit_marker(self):
        self.window.apply_frame({"schema": 1, "status": "ok", "live": True})
        self.assertIn("LIVE", self.window.header.connection.text())

    def test_the_profile_is_shown_when_observed(self):
        self.window.apply_frame(
            {"schema": 1, "profile": "vanilla-2.1.23", "gameVersion": "2.1.23"})
        self.assertIn("vanilla-2.1.23", self.window.header.profile.text())

    def test_the_profile_says_unknown_when_it_was_not_observed(self):
        self.window.apply_frame({"schema": 1})
        self.assertIn("unknown", self.window.header.profile.text().lower())

    def test_absent_metrics_are_not_rendered_as_zero(self):
        self.window.apply_frame({"schema": 1})
        for name in ("UPS", "Power", "Production"):
            tile = self.window.header.tiles[name]
            self.assertEqual(tile.value.text(), "—")
            self.assertNotEqual(tile.value.text(), "0")

    def test_an_observed_metric_shows_its_number_and_badge(self):
        self.window.apply_frame({"schema": 1, "ups": 60.0})
        tile = self.window.header.tiles["UPS"]
        self.assertEqual(tile.value.text(), "60.00")
        self.assertEqual(tile.badge.text(), "observed")

    def test_an_unavailable_metric_is_badged_as_unavailable(self):
        self.window.apply_frame({"schema": 1})
        tile = self.window.header.tiles["UPS"]
        self.assertEqual(tile.badge.text(), "unavailable")

    def test_the_freshness_is_shown(self):
        self.window.apply_frame({"schema": 1}, age_seconds=5.0)
        self.assertIn("Fresh", self.window.header.freshness.text())

    def test_a_stale_observation_is_shown_as_stale(self):
        self.window.apply_frame({"schema": 1}, age_seconds=300.0)
        self.assertIn("Stale", self.window.header.freshness.text())

    def test_the_header_layout_is_responsive(self):
        """A narrow window must not break the header's own layout."""
        self.window.resize(1100, 700)
        self.window.show()
        self.app.processEvents()
        self.assertGreaterEqual(self.window.header.height(), 40)

    def test_the_window_survives_a_resize(self):
        for width, height in ((1100, 700), (2560, 1440), (1440, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertEqual(self.window.width(), width)
            self.assertEqual(self.window.height(), height)

    def test_the_window_closes_cleanly(self):
        self.window.show()
        self.app.processEvents()
        self.window.close()
        self.app.processEvents()

    def test_the_shell_has_no_gameplay_write_path(self):
        """The shell must not be able to command the game.

        The check looks at the module's *code*, not its prose: the
        docstring legitimately says that the shell has no RCON client.
        """
        import ast

        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_shell.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Attribute):
                    called.add(function.attr)
                elif isinstance(function, ast.Name):
                    called.add(function.id)
        for forbidden in ("call_tool", "send_command", "place_entity",
                          "execute_command", "rcon"):
            self.assertNotIn(forbidden, called)

    def test_the_shell_imports_no_transport_module(self):
        """The shell must not import a game transport at all."""
        import ast

        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_shell.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for forbidden in ("observation_service", "observation_coordinator",
                          "dispatch_boundary", "dashboard_feed", "rcon_client"):
            self.assertNotIn(forbidden, imported)

    def test_blueprint_workspace_contains_functional_editor(self):
        from qt_blueprint_workspace import BlueprintWorkspace

        workspace = self.window.blueprint_workspace()
        self.assertIsInstance(workspace, BlueprintWorkspace)
        self.assertIsNotNone(workspace.tree)
        self.assertIsNotNone(workspace.studio.preview)
        self.assertIsNotNone(workspace.generate_button)

    def test_blueprint_without_catalog_reports_missing_observations(self):
        """An unobserved catalog cannot be mistaken for build-ready facts."""
        workspace = self.window.blueprint_workspace()
        self.assertFalse(workspace.generate())
        self.assertIn("complete", workspace.message.text().lower())


class _FakeClock:
    """A controllable clock, so freshness can be tested without waiting."""

    def __init__(self, now: float = 0.0):
        self.now = float(now)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += float(seconds)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class MetricStateRegressionTests(unittest.TestCase):
    """The metric tiles keep independent, persistent state.

    These are the regressions for the confirmed metric-state bug: the
    header used to rebuild every tile from the original frame whenever a
    single observation arrived, so a later Power reading erased a valid
    UPS reading.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = qt_shell.ShellWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    @staticmethod
    def _observed(value, detail="Observed", source=""):
        from qt_observation import observed

        return observed(value, detail, source=source)

    def _tile_text(self, name):
        return self.window.header.tiles[name].value.text()

    def _badge_text(self, name):
        return self.window.header.tiles[name].badge.text()

    # -- the confirmed reproduction ---------------------------------------

    def test_a_power_update_does_not_erase_the_ups_observation(self):
        """The confirmed bug: updating Power must not erase the UPS.

        Reproduction: apply an initial frame, update the UPS to 60, update
        the Power to 100, and the UPS must still read 60.
        """
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.window.apply_observation(observed(100.0, "Observed"), "Power")
        self.assertEqual(self._tile_text("UPS"), "60.00")
        self.assertEqual(self._tile_text("Power"), "100.00")

    def test_consecutive_updates_of_three_metrics_all_survive(self):
        """Three consecutive metric updates must all be visible."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.window.apply_observation(observed(100.0, "Observed"), "Power")
        self.window.apply_observation(observed(12.5, "Observed"), "Production")
        self.assertEqual(self._tile_text("UPS"), "60.00")
        self.assertEqual(self._tile_text("Power"), "100.00")
        self.assertEqual(self._tile_text("Production"), "12.50")

    def test_a_repeated_update_of_one_metric_replaces_only_that_metric(self):
        """A newer value of one metric replaces that metric alone."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.window.apply_observation(observed(100.0, "Observed"), "Power")
        self.window.apply_observation(observed(59.0, "Observed"), "UPS")
        self.assertEqual(self._tile_text("UPS"), "59.00")
        self.assertEqual(self._tile_text("Power"), "100.00")

    def test_a_frame_seeds_the_metrics_it_carries(self):
        """A frame's own numbers reach the tiles."""
        self.window.apply_frame(
            {"schema": 1, "ups": 60.0, "power": {"consumption": 250.0}})
        self.assertEqual(self._tile_text("UPS"), "60.00")
        self.assertEqual(self._tile_text("Power"), "250.00")

    def test_a_frame_without_a_metric_does_not_clear_an_observed_one(self):
        """A later frame that omits a metric must not erase it."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.window.apply_frame({"schema": 1, "status": "ok"})
        self.assertEqual(self._tile_text("UPS"), "60.00")

    # -- missing data -----------------------------------------------------

    def test_a_metric_that_was_never_observed_is_unavailable(self):
        """An unobserved metric is an em dash, never a zero."""
        self.window.apply_frame({"schema": 1})
        self.assertEqual(self._tile_text("UPS"), "—")
        self.assertNotEqual(self._tile_text("UPS"), "0")
        self.assertEqual(self._badge_text("UPS"), "unavailable")

    def test_an_unavailable_observation_is_not_rendered_as_zero(self):
        """An explicit unavailable observation stays unknown."""
        from qt_observation import unavailable

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(unavailable("Not reported"), "UPS")
        self.assertEqual(self._tile_text("UPS"), "—")
        self.assertEqual(self._badge_text("UPS"), "unavailable")

    # -- ordering ---------------------------------------------------------

    def test_an_out_of_order_observation_is_rejected(self):
        """A late packet must not overwrite a newer reading."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        accepted = self.window.apply_observation(
            observed(10.0, "Observed"), "UPS", timestamp=0.0)
        self.assertFalse(accepted)
        self.assertEqual(self._tile_text("UPS"), "60.00")

    def test_an_in_order_observation_is_accepted(self):
        """A newer observation replaces the older one."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(
            observed(60.0, "Observed"), "UPS", timestamp=100.0)
        accepted = self.window.apply_observation(
            observed(59.0, "Observed"), "UPS", timestamp=200.0)
        self.assertTrue(accepted)
        self.assertEqual(self._tile_text("UPS"), "59.00")

    # -- staleness --------------------------------------------------------

    def test_an_aged_out_metric_becomes_stale_and_keeps_its_number(self):
        """A value that outlived its window is stale, not current."""
        from qt_observation import observed

        state = qt_shell.MetricState(ttl=1.0, clock=lambda: 1000.0)
        state.update("UPS", observed(60.0, "Observed"), timestamp=0.0)
        aged = state.refresh("UPS")
        self.assertEqual(aged.state, "stale")
        self.assertEqual(aged.value, 60.0)

    def test_a_fresh_metric_is_not_aged_out(self):
        """A value inside its window stays observed."""
        from qt_observation import observed

        state = qt_shell.MetricState(ttl=30.0, clock=lambda: 10.0)
        state.update("UPS", observed(60.0, "Observed"), timestamp=0.0)
        self.assertEqual(state.refresh("UPS").state, "observed")
        self.assertTrue(state.is_fresh("UPS"))

    def test_refreshing_the_window_shows_the_stale_badge(self):
        """The header shows the stale badge once the value aged out."""
        from qt_observation import observed

        clock = _FakeClock()
        window = qt_shell.ShellWindow(
            metric_state=qt_shell.MetricState(ttl=30.0, clock=clock))
        try:
            window.apply_frame({"schema": 1})
            window.apply_observation(observed(60.0, "Observed"), "UPS")
            self.assertEqual(window.header.tiles["UPS"].badge.text(), "observed")
            clock.advance(120.0)
            window.refresh_metrics()
            self.assertEqual(window.header.tiles["UPS"].badge.text(), "stale")
            self.assertEqual(window.header.tiles["UPS"].value.text(), "60.00")
        finally:
            window.close()
            window.deleteLater()

    # -- disconnect and reconnect -----------------------------------------

    def test_a_confirmed_disconnect_drops_the_old_numbers(self):
        """A disconnected observer must not leave a misleading number."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.window.apply_disconnect("Observer disconnected")
        self.assertEqual(self._tile_text("UPS"), "—")
        self.assertEqual(self._badge_text("UPS"), "unavailable")

    def test_a_reconnect_restores_the_metric(self):
        """After a reconnect the observer's value is shown again."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.window.apply_disconnect("Observer disconnected")
        self.window.apply_observation(observed(59.0, "Observed"), "UPS")
        self.assertEqual(self._tile_text("UPS"), "59.00")
        self.assertEqual(self._badge_text("UPS"), "observed")

    def test_a_reconnect_does_not_resurrect_a_stale_value(self):
        """A reconnect starts from nothing, not from the old number."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        self.window.apply_disconnect("Observer disconnected")
        self.assertEqual(self._tile_text("UPS"), "—")
        self.assertIsNone(self.window.metric_state.timestamp("UPS"))

    # -- provenance -------------------------------------------------------

    def test_each_metric_tracks_its_own_source(self):
        """The source of each metric is tracked separately."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(
            observed(60.0, "Observed", source="ups"), "UPS")
        self.window.apply_observation(
            observed(100.0, "Observed", source="power"), "Power")
        self.assertEqual(self.window.metric_state.source("UPS"), "ups")
        self.assertEqual(self.window.metric_state.source("Power"), "power")

    def test_each_metric_tracks_its_own_timestamp(self):
        """The timestamp of each metric is tracked separately."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(
            observed(60.0, "Observed"), "UPS", timestamp=100.0)
        self.window.apply_observation(
            observed(100.0, "Observed"), "Power", timestamp=200.0)
        self.assertEqual(self.window.metric_state.timestamp("UPS"), 100.0)
        self.assertEqual(self.window.metric_state.timestamp("Power"), 200.0)

    def test_the_metric_state_starts_empty(self):
        """A new shell knows no metric at all."""
        self.assertEqual(self.window.metric_state.names(), ())
        self.assertIsNone(self.window.metric_state.timestamp("UPS"))


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class UiFrameApplicationTests(unittest.TestCase):
    """The shell routes the bridge's validated frames."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = qt_shell.ShellWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    @staticmethod
    def _frame(kind, value=None, **kwargs):
        from qt_observation_bridge import UiFrame

        return UiFrame(kind=kind, value=value, **kwargs)

    def test_a_status_frame_updates_the_metric_tiles(self):
        """A status frame carries the observed metric values."""
        frame = self._frame(
            "status", {"tick": 5, "ups": 60.0, "power": {"consumption": 100.0}},
            state="observed")
        self.window.apply_ui_frame(frame)
        self.assertEqual(self.window.header.tiles["UPS"].value.text(), "60.00")

    def test_factory_map_navigation_requests_bounded_visible_chunks(self):
        from unittest.mock import Mock

        bridge = Mock()
        self.window._bridge = bridge
        self.window.show_workspace("Factory Map")
        requested = bridge.request_map.call_args.args[0]
        self.assertTrue(requested)
        self.assertLessEqual(len(requested), 16)
        self.window.show_workspace("Overview")
        bridge.request_map.reset_mock()
        self.window.request_visible_map()
        bridge.request_map.assert_not_called()
        self.window._bridge = None

    def test_map_frames_are_scoped_to_the_current_surface(self):
        from unittest.mock import patch

        from test_dashboard_chunk_cache import frame

        self.window._current_frame = {"surface": "nauvis"}
        payload = {"surface": "nauvis", "tick": 1, "terrain": frame()}
        with patch.object(self.window, "set_map") as display:
            self.window.apply_ui_frame(self._frame("map", payload, state="observed"))
            display.assert_called_once()
            display.reset_mock()
            payload["surface"] = "other"
            self.window.apply_ui_frame(self._frame("map", payload, state="observed"))
            display.assert_not_called()

    def test_a_telemetry_frame_reaches_the_telemetry_workspaces(self):
        """A telemetry frame is shown in the telemetry workspaces."""
        frame = self._frame(
            "telemetry",
            {"tick": 5, "flows": [], "networks": []},
            state="observed")
        self.window.apply_ui_frame(frame)

    def test_a_stale_telemetry_frame_cannot_look_current(self):
        from unittest.mock import patch

        frame = self._frame("telemetry", {"tick": 5}, state="stale", age_seconds=1)
        with patch.object(self.window, "set_telemetry") as display:
            self.window.apply_ui_frame(frame)
        display.assert_called_once_with(None, age_seconds=1)

    def test_a_disconnected_frame_clears_the_metrics(self):
        """A disconnect must not leave a misleading number on screen."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        frame = self._frame("status", None, state="unavailable",
                            detail="Disconnected")
        self.window.apply_ui_frame(frame)
        self.assertEqual(self.window.header.tiles["UPS"].value.text(), "—")

    def test_an_unknown_frame_keeps_the_metrics_but_not_as_current(self):
        """A failed observation does not invent a value."""
        from qt_observation import observed

        self.window.apply_frame({"schema": 1})
        self.window.apply_observation(observed(60.0, "Observed"), "UPS")
        frame = self._frame("status", None, state="unavailable",
                            detail="Observation failed")
        self.window.apply_ui_frame(frame)
        self.assertNotEqual(self.window.header.tiles["UPS"].value.text(), "0")

    def test_a_stale_frame_does_not_claim_to_be_observed(self):
        """A stale frame is not presented as a current observation."""
        frame = self._frame("status", {"tick": 5, "ups": 60.0}, state="stale")
        self.window.apply_ui_frame(frame)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class LiveObservationTests(unittest.TestCase):
    """The shell starts the bridge and routes its frames."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = qt_shell.ShellWindow()

    def tearDown(self):
        self.window.stop_observations()
        self.window.close()
        self.window.deleteLater()

    class _FakeBridge:
        """A bridge stand-in that records how the shell drives it."""

        def __init__(self):
            self.started = None
            self.stopped = False
            self.on_frame: Any = None
            self.on_error: Any = None

        def start(self, session, on_frame, on_error=None):
            self.started = session
            self.on_frame = on_frame
            self.on_error = on_error
            return None

        def stop(self, timeout=5.0):
            self.stopped = True

        def publish(self, frame):
            """Deliver one frame the way the real worker does."""
            self.on_frame(frame)

        def fail(self, error):
            """Deliver one error the way the real worker does."""
            self.on_error(error)

        def request_catalog(self, page=1, *, page_size=16, refresh=False):
            """Record one user-driven catalog request."""
            self.catalog_request = (page, page_size, refresh)
            return True

    def test_the_refresh_button_asks_the_bridge_for_the_catalog(self):
        """The button starts a request; it never fetches by itself."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        self.window.catalog_widget().refresh_button.click()
        self.assertEqual(bridge.catalog_request, (1, 128, True))

    def test_the_load_more_button_asks_for_the_next_page(self):
        """Load more is enabled only after the game reported more pages."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        payload = {
            "catalog_status": {"status": "ok", "page": 1, "page_size": 16,
                               "total_count": 40, "total_pages": 3},
            "capabilities": {
                "recipes": [{"name": "iron-gear-wheel", "enabled": True,
                             "hidden": False, "category": "crafting"}],
                "machines": [], "research": [], "truncated": False,
            },
        }
        bridge.publish(UiFrame(kind="catalog", value=payload,
                               state="observed", detail="Observed catalog"))
        self.assertTrue(
            self.window.catalog_widget().load_more_button.isEnabled())
        self.window.catalog_widget().load_more_button.click()
        self.assertEqual(bridge.catalog_request[0], 2)

    def test_a_catalog_request_without_a_bridge_is_refused(self):
        self.assertFalse(self.window.request_catalog_refresh())
        self.assertFalse(self.window.request_catalog_more())

    def test_a_catalog_frame_is_shown_in_the_recipe_workspace(self):
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        payload = {
            "catalog_status": {"status": "ok", "page": 1, "page_size": 16,
                               "total_count": 1, "total_pages": 1},
            "capabilities": {
                "recipes": [{"name": "iron-gear-wheel", "enabled": True,
                             "hidden": False, "category": "crafting"}],
                "machines": [], "research": [], "truncated": False,
            },
        }
        bridge.publish(UiFrame(kind="catalog", value=payload,
                               state="observed", detail="Observed catalog"))
        self.assertEqual(self.window.catalog_widget().recipe_table.rowCount(), 1)
        self.assertEqual(
            self.window.catalog_widget().recipe_table.item(0, 0).text(),
            "iron-gear-wheel")

    def test_a_failed_catalog_frame_is_reported_as_unavailable(self):
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        bridge.publish(UiFrame(kind="catalog", value=None,
                               state="unavailable", detail="not observed"))
        self.assertIn("unavailable",
                      self.window.catalog_widget().status.text().lower())

    def test_disconnect_invalidates_catalog_based_planning(self):
        from test_qt_blueprint_workspace import FRAME
        self.window.set_catalog(FRAME)
        workspace = self.window.blueprint_workspace()
        self.assertIsNotNone(workspace)
        catalog = workspace.catalog
        self.assertIsNotNone(catalog)
        assert catalog is not None
        self.assertTrue(catalog.complete)
        self.window.apply_disconnect("connection lost")
        workspace = self.window.blueprint_workspace()
        self.assertIsNotNone(workspace)
        catalog = workspace.catalog
        self.assertIsNotNone(catalog)
        assert catalog is not None
        self.assertFalse(catalog.complete)
        snapshot = self.window.catalog_widget().snapshot
        assert snapshot is not None
        self.assertEqual(snapshot.state, "stale")
        self.assertFalse(snapshot.complete)

    def test_a_status_frame_does_not_erase_the_observed_catalog(self):
        """A status frame carries no catalog and must not clear the rows."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        payload = {
            "catalog_status": {"status": "ok", "page": 1, "page_size": 16,
                               "total": 662, "page_count": 42},
            "capabilities": {
                "recipes": [{"name": "iron-gear-wheel", "enabled": True,
                             "hidden": False, "category": "crafting"}],
                "research": [{"name": "automation"}],
            },
        }
        bridge.publish(UiFrame(kind="catalog", value=payload,
                               state="observed", detail="Observed catalog"))
        self.assertEqual(self.window.catalog_widget().recipe_table.rowCount(), 1)
        # A later status frame must not replace the catalog with nothing.
        bridge.publish(UiFrame(kind="status", value={"tick": 5,
                                                      "surface": "nauvis"},
                               state="observed", detail="Observed status"))
        self.assertEqual(self.window.catalog_widget().recipe_table.rowCount(), 1)
        self.assertNotIn("unavailable",
                         self.window.catalog_widget().status.text().lower())

    def test_the_inventory_and_logistics_workspaces_are_implemented(self):
        from qt_inventory_widget import InventoryWidget

        self.assertIsInstance(
            self.window.inventory_widget("Inventory"), InventoryWidget)
        self.assertIsInstance(
            self.window.inventory_widget("Logistics"), InventoryWidget)

    def test_both_inventory_workspaces_consume_the_same_frame(self):
        frame = {
            "status": "ok", "tick": 5, "inventory_available": True,
            "capacity": 40, "truncated": False, "slots_truncated": False,
            "inventory": [{"name": "iron-plate", "quality": "normal",
                           "count": 7}],
        }
        self.window.apply_frame(frame)
        for workspace in ("Inventory", "Logistics"):
            widget = self.window.inventory_widget(workspace)
            self.assertEqual(widget.inventory_table.rowCount(), 1)
            self.assertEqual(
                widget.inventory_table.item(0, 2).text(), "7")

    def test_the_shell_starts_the_bridge_with_the_session(self):
        """The shell hands the bridge the session it was given."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        self.assertEqual(bridge.started, "session")

    def test_starting_twice_is_refused(self):
        """A second bridge is refused."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        with self.assertRaises(RuntimeError):
            self.window.start_observations(self._FakeBridge(), "session")

    def test_a_frame_from_the_bridge_reaches_the_header(self):
        """A frame published by the bridge is routed to the header."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        from qt_observation_bridge import UiFrame

        bridge.publish(UiFrame(
            kind="status", value={"tick": 5, "ups": 60.0}, state="observed"))
        self.app.processEvents()
        self.assertEqual(self.window.header.tiles["UPS"].value.text(), "60.00")

    def test_stopping_releases_the_bridge(self):
        """Stopping the shell stops the bridge."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        self.window.stop_observations()
        self.assertTrue(bridge.stopped)

    def test_closing_the_window_stops_the_bridge(self):
        """The worker is stopped when the window closes."""
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        self.window.show()
        self.app.processEvents()
        self.window.close()
        self.app.processEvents()
        self.assertTrue(bridge.stopped)

    def test_an_observation_error_is_reported(self):
        """A failed observation is reported, not swallowed."""
        errors = []
        self.window.observationError.connect(errors.append)
        bridge = self._FakeBridge()
        self.window.start_observations(bridge, "session")
        bridge.fail(ValueError("boom"))
        self.app.processEvents()
        self.assertTrue(errors)
        self.assertIn("boom", errors[0])

    def test_the_shell_still_has_no_write_path(self):
        """Connecting the observation path did not add a gameplay path."""
        import ast

        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_shell.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Attribute):
                    called.add(function.attr)
                elif isinstance(function, ast.Name):
                    called.add(function.id)
        for forbidden in ("call_tool", "send_command", "place_entity",
                          "execute_command", "rcon"):
            self.assertNotIn(forbidden, called)


if __name__ == "__main__":
    unittest.main()
