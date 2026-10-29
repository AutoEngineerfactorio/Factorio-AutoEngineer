"""Regression tests for the Qt theme, the header state and the metric tiles.

These tests import no Qt module and need no display server: the theme and
the header's truthfulness rules are pure logic, and they must stay
verifiable when the graphical dashboard cannot run.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import qt_observation  # noqa: E402
import qt_theme  # noqa: E402


class ConnectionIndicatorTests(unittest.TestCase):
    """The indicator is never optimistic."""

    def test_no_frame_is_offline(self):
        self.assertEqual(qt_theme.connection_state(None), qt_theme.OFFLINE)
        self.assertEqual(qt_theme.connection_state({}), qt_theme.OFFLINE)

    def test_unavailable_frame_is_unavailable(self):
        self.assertEqual(
            qt_theme.connection_state({"status": "unavailable"}),
            qt_theme.UNAVAILABLE_STATE,
        )

    def test_a_frame_is_a_snapshot_not_a_live_connection(self):
        state = qt_theme.connection_state({"schema": 1, "status": "ok"})
        self.assertEqual(state, qt_theme.SNAPSHOT)
        self.assertNotEqual(state, qt_theme.LIVE)

    def test_live_requires_an_explicit_marker(self):
        self.assertEqual(
            qt_theme.connection_state({"live": True}), qt_theme.LIVE)

    def test_every_connection_state_has_a_label_and_a_colour(self):
        for state in qt_theme.CONNECTION_STATES:
            self.assertIn(state, qt_theme.CONNECTION_LABELS)
            self.assertIn(state, qt_theme.CONNECTION_COLORS)

    def test_profile_label_uses_only_observed_fields(self):
        label = qt_theme.profile_label(
            {"profile": "vanilla-2.1.23", "gameVersion": "2.1.23"})
        self.assertIn("vanilla-2.1.23", label)
        self.assertIn("2.1.23", label)

    def test_profile_label_says_unknown_without_a_profile(self):
        self.assertEqual(qt_theme.profile_label({}), "Profile unknown")
        self.assertEqual(qt_theme.profile_label(None), "Profile unknown")

    def test_freshness_label_distinguishes_fresh_from_stale(self):
        self.assertIn("Fresh", qt_theme.freshness_label(0.4))
        self.assertIn("Fresh", qt_theme.freshness_label(30.0))
        self.assertIn("Stale", qt_theme.freshness_label(300.0))
        self.assertEqual(
            qt_theme.freshness_label(float("inf")), "Freshness unknown")
        self.assertEqual(
            qt_theme.freshness_label(None), "Freshness unknown")


class HeaderStateTests(unittest.TestCase):
    """The header never claims a connection it does not have."""

    def test_header_reports_the_helper_read_only_mode(self):
        header = qt_theme.build_header_state({"schema": 1})
        self.assertEqual(header.mode, qt_theme.HELPER)
        self.assertIn("READ ONLY", header.mode_text)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            qt_theme.build_header_state({}, mode="anything")

    def test_header_snapshot_is_not_live(self):
        header = qt_theme.build_header_state({"schema": 1, "status": "ok"})
        self.assertEqual(header.connection, qt_theme.SNAPSHOT)
        self.assertNotIn("LIVE", header.connection_text)

    def test_full_autonomy_is_shown_as_locked(self):
        header = qt_theme.build_header_state({}, mode=qt_theme.FULL)
        self.assertIn("LOCKED", header.mode_text)

    def test_header_carries_the_freshness_text(self):
        header = qt_theme.build_header_state({}, age_seconds=120.0)
        self.assertIn("Stale", header.freshness_text)


class MetricTileTests(unittest.TestCase):
    """Header metrics separate observed from absent."""

    def test_missing_metrics_are_unavailable_not_zero(self):
        tiles = qt_theme.build_metric_tiles({"schema": 1})
        by_name = {tile.name: tile for tile in tiles}
        for name in ("UPS", "Power", "Production"):
            self.assertFalse(by_name[name].observation.known)
            self.assertEqual(by_name[name].value_text, "—")
            self.assertNotEqual(by_name[name].value_text, "0")

    def test_observed_ups_is_shown(self):
        tiles = qt_theme.build_metric_tiles({"ups": 60.0})
        by_name = {tile.name: tile for tile in tiles}
        self.assertTrue(by_name["UPS"].observation.known)
        self.assertEqual(by_name["UPS"].observation.state, qt_observation.OBSERVED)

    def test_unavailable_production_reason_is_preserved(self):
        tiles = qt_theme.build_metric_tiles(
            {"production": {"status": "unavailable", "reason": "No telemetry"}})
        by_name = {tile.name: tile for tile in tiles}
        self.assertFalse(by_name["Production"].observation.known)
        self.assertEqual(by_name["Production"].observation.detail, "No telemetry")

    def test_power_satisfaction_is_surfaced_when_observed(self):
        tiles = qt_theme.build_metric_tiles(
            {"power": {"consumption": 100.0, "satisfaction": 0.92}})
        by_name = {tile.name: tile for tile in tiles}
        detail = by_name["Power"].observation.detail
        self.assertIn("92.0%", detail)
        self.assertTrue(by_name["Power"].observation.known)

    def test_power_without_satisfaction_stays_observed(self):
        tiles = qt_theme.build_metric_tiles({"power": {"consumption": 100.0}})
        by_name = {tile.name: tile for tile in tiles}
        self.assertTrue(by_name["Power"].observation.known)
        self.assertNotIn("satisfaction", by_name["Power"].observation.detail)

    def test_badge_object_name_matches_the_state(self):
        for state, expected in (
            (qt_observation.OBSERVED, "badgeObserved"),
            (qt_observation.ESTIMATED, "badgeEstimated"),
            (qt_observation.STALE, "badgeStale"),
            (qt_observation.UNAVAILABLE, "badgeUnavailable"),
        ):
            observation = qt_observation.Observation(
                value=1.0, state=state, detail="d")
            tile = qt_theme.MetricTile(name="UPS", observation=observation)
            self.assertEqual(tile.badge_object_name, expected)

    def test_every_badge_object_name_is_styled(self):
        for state in qt_observation.OBSERVATION_STATES:
            observation = qt_observation.Observation(
                value=1.0, state=state, detail="d")
            name = qt_theme.MetricTile(
                name="X", observation=observation).badge_object_name
            self.assertIn(name, qt_theme.STYLESHEET)


class PaletteTests(unittest.TestCase):
    """The palette is a real, self-consistent set of colours."""

    def test_every_palette_value_is_a_hex_colour(self):
        for name in dir(qt_theme.Palette):
            if name.startswith("_"):
                continue
            value = getattr(qt_theme.Palette, name)
            if isinstance(value, str) and name.isupper():
                self.assertRegex(value, r"^#[0-9a-f]{6}$", name)

    def test_chart_series_are_distinct(self):
        series = qt_theme.Palette.CHART_SERIES
        self.assertEqual(len(series), len(set(series)))
        self.assertGreaterEqual(len(series), 4)

    def test_stylesheet_uses_the_palette(self):
        self.assertIn(qt_theme.Palette.WINDOW, qt_theme.STYLESHEET)
        self.assertIn(qt_theme.Palette.ACCENT, qt_theme.STYLESHEET)

    def test_stylesheet_has_no_unresolved_placeholder(self):
        """A leftover ``{Palette.NAME}`` would render as literal text."""
        unresolved = re.findall(
            r"\{[A-Za-z_][A-Za-z0-9_.]*\}", qt_theme.STYLESHEET)
        self.assertEqual(unresolved, [], f"unresolved placeholders: {unresolved}")

    def test_theme_module_does_not_import_qt(self):
        """The theme must stay testable without a display server."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_theme.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("PySide6", source)
        self.assertNotIn("QtWidgets", source)

    def test_the_state_model_module_does_not_import_qt(self):
        """The observation state model must also stay headless-testable."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_observation.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("PySide6", source)
        self.assertNotIn("QtWidgets", source)

    def test_the_theme_exports_the_telemetry_series(self):
        self.assertIn("TelemetrySeries", qt_theme.__all__)
        self.assertIn("series_color", qt_theme.__all__)


class TelemetrySeriesTests(unittest.TestCase):
    """The chart series stay bounded and never store a broken sample."""

    def test_a_new_series_has_no_latest_value(self):
        series = qt_theme.TelemetrySeries("iron-plate")
        self.assertIsNone(series.latest)
        self.assertEqual(series.points, [])

    def test_appending_records_the_sample_in_order(self):
        series = qt_theme.TelemetrySeries("iron-plate")
        series.append(1.0)
        series.append(3.0)
        self.assertEqual(series.points, [1.0, 3.0])
        self.assertEqual(series.latest, 3.0)

    def test_the_series_is_bounded_and_drops_the_oldest(self):
        series = qt_theme.TelemetrySeries("iron-plate", maximum_points=3)
        for value in range(5):
            series.append(float(value))
        self.assertEqual(series.points, [2.0, 3.0, 4.0])
        self.assertEqual(series.latest, 4.0)

    def test_a_non_finite_sample_is_rejected(self):
        series = qt_theme.TelemetrySeries("iron-plate")
        with self.assertRaises(ValueError):
            series.append(float("nan"))
        with self.assertRaises(ValueError):
            series.append(float("inf"))
        self.assertEqual(series.points, [])

    def test_a_non_numeric_sample_is_rejected(self):
        series = qt_theme.TelemetrySeries("iron-plate")
        with self.assertRaises(ValueError):
            series.append("1.0")
        with self.assertRaises(ValueError):
            series.append(True)

    def test_a_series_must_keep_at_least_one_point(self):
        series = qt_theme.TelemetrySeries("iron-plate", maximum_points=0)
        with self.assertRaises(ValueError):
            series.append(1.0)

    def test_series_colours_cycle_through_the_palette(self):
        palette = qt_theme.Palette.CHART_SERIES
        self.assertEqual(qt_theme.series_color(0), palette[0])
        self.assertEqual(qt_theme.series_color(len(palette)), palette[0])
        self.assertEqual(qt_theme.series_color(1), palette[1])

    def test_a_negative_series_index_is_rejected(self):
        with self.assertRaises(ValueError):
            qt_theme.series_color(-1)

    def test_the_series_colour_is_a_palette_colour(self):
        self.assertIn(
            qt_theme.series_color(0), qt_theme.Palette.CHART_SERIES)


if __name__ == "__main__":
    unittest.main()
