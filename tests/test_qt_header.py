"""Regression tests for the Qt header widgets.

These tests need PySide6. They run on the **offscreen** platform plugin so
they need no display server, and they skip cleanly when PySide6 is not
installed, so the offline suite still passes in an environment without the
optional UI dependency.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication

    import qt_header
    import qt_observation

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class HeaderWidgetTests(unittest.TestCase):
    """The header shows the truth about every number it renders."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.header = qt_header.HeaderWidget()

    def tearDown(self):
        self.header.close()
        self.header.deleteLater()

    def test_the_header_starts_in_the_offline_read_only_state(self):
        self.assertIn("OFFLINE", self.header.connection.text())
        self.assertIn("READ ONLY", self.header.mode.text())

    def test_the_profile_starts_unknown(self):
        self.assertIn("unknown", self.header.profile.text().lower())

    def test_the_freshness_starts_unknown(self):
        self.assertIn("unknown", self.header.freshness.text().lower())

    def test_a_metric_tile_shows_its_value_and_badge(self):
        tile = qt_header.MetricTileWidget(qt_theme_tile(60.0))
        self.assertEqual(tile.value.text(), "60.00")
        self.assertEqual(tile.badge.text(), "observed")

    def test_an_unavailable_tile_shows_an_em_dash_not_zero(self):
        tile = qt_header.MetricTileWidget(qt_theme_tile(None))
        self.assertEqual(tile.value.text(), "—")
        self.assertNotEqual(tile.value.text(), "0")
        self.assertEqual(tile.badge.text(), "unavailable")

    def test_updating_a_tile_changes_the_rendered_value(self):
        tile = qt_header.MetricTileWidget(qt_theme_tile(1.0))
        tile.update_tile(qt_theme_tile(2.0))
        self.assertEqual(tile.value.text(), "2.00")

    def test_updating_a_tile_with_the_same_value_keeps_it(self):
        tile = qt_header.MetricTileWidget(qt_theme_tile(1.0))
        tile.update_tile(qt_theme_tile(1.0))
        self.assertEqual(tile.value.text(), "1.00")

    def test_the_tiles_are_created_once_and_reused(self):
        from qt_theme import build_metric_tiles

        tiles = build_metric_tiles({"schema": 1})
        self.header.apply_metric_tiles(tiles)
        widget = self.header.tiles["UPS"]
        self.header.apply_metric_tiles(build_metric_tiles({"schema": 1}))
        self.assertIs(self.header.tiles["UPS"], widget)

    def test_the_tiles_follow_the_observation_state(self):
        from qt_theme import build_metric_tiles

        self.header.apply_metric_tiles(build_metric_tiles({"schema": 1}))
        self.assertEqual(self.header.tiles["UPS"].badge.text(), "unavailable")
        self.header.apply_metric_tiles(build_metric_tiles({"ups": 60.0}))
        self.assertEqual(self.header.tiles["UPS"].badge.text(), "observed")

    def test_the_header_shows_the_connection_colour(self):
        from qt_theme import build_header_state

        state = build_header_state({"status": "unavailable"})
        self.header.apply_header_state(state)
        self.assertIn("UNAVAILABLE", self.header.connection.text())
        self.assertTrue(self.header.connection.styleSheet())

    def test_the_header_uses_a_fixed_number_of_tiles_per_row(self):
        self.assertEqual(qt_header.METRICS_PER_ROW, 4)


    def test_reference_header_displays_observed_version_and_locked_stop(self):
        self.header.apply_game_context({"capabilities":{"game_version":"2.1.23"}})
        self.assertEqual(self.header.version.text(),"2.1.23")
        self.assertFalse(self.header.stop_ai.isEnabled())
        self.assertEqual(set(self.header.tools),{"Notifications","Diagnostics","Settings"})


def qt_theme_tile(value):
    """Return a metric tile for one value, observed or unavailable."""
    from qt_theme import MetricTile

    if value is None:
        return MetricTile("UPS", qt_observation.unavailable())
    return MetricTile("UPS", qt_observation.observed(value, "Observed snapshot"))




if __name__ == "__main__":
    unittest.main()
