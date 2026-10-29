"""Regression tests for the Qt telemetry widget.

These tests need PySide6. They run on the **offscreen** platform plugin so
they need no display server, and they skip cleanly when PySide6 is not
installed, so the offline suite still passes without the optional UI
dependency.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication

    import qt_telemetry_widget

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


def _group(cap, series, prototype_count=None):
    """Return one validated flow group."""
    count = cap if prototype_count is None else prototype_count
    return {
        "status": "ok",
        "unit": "units_per_minute",
        "precision": "ten_minutes",
        "sample_interval_seconds": 2,
        "sample_count": 60,
        "window_seconds": 120,
        "prototype_count": count,
        "candidate_cap": cap,
        "candidate_bucket": 1,
        "candidate_bucket_count": max(1, -(-count // cap)),
        "partial": count > cap,
        "series": series,
    }


def _telemetry(tick=123, satisfaction=0.9, production=1000, consumption=900,
               surface=None):
    """Return one validated telemetry payload.

    The ``surface`` is a **sibling** of the validated envelope, exactly
    as the mod reports it.
    """
    payload = {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": "partial",
            "reason": "Only one bounded prototype bucket is sampled",
            "items": _group(128, [{
                "name": "iron-plate",
                "input": [2.0] * 60,
                "output": [10.0] * 60,
            }], prototype_count=130),
            "fluids": _group(64, []),
        },
        "power": {
            "status": "ok",
            "unit": "joules_per_tick",
            "tick": tick,
            "networks": [{
                "network_id": 1,
                "tick": tick,
                "maximum_production": production,
                "maximum_consumption": consumption,
                "consumption_satisfaction": satisfaction,
                "production_satisfaction": 1,
                "accumulator_energy": 0,
                "accumulator_capacity": 0,
            }],
            "partial": False,
        },
    }
    if surface is not None:
        payload["surface"] = surface
    return payload


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class TelemetryWidgetTests(unittest.TestCase):
    """The widget shows the observed telemetry in its tables."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_telemetry_widget.TelemetryWidget()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def _cells(self, table, row=0):
        """Return the text of every cell of one row."""
        return [table.item(row, column).text()
                for column in range(table.columnCount())]

    def test_the_flow_table_shows_the_observed_row(self):
        """The production table shows the observed material."""
        self.widget.set_telemetry(_telemetry())
        self.assertEqual(self.widget.flow_table.rowCount(), 1)
        self.assertEqual(self._cells(self.widget.flow_table)[0], "iron-plate")

    def test_the_electrical_table_shows_the_observed_network(self):
        """The electrical table shows the observed network.

        This is the regression for the empty electrical table: the column
        headers are labels a user reads, while the display mapping is keyed
        by the name the telemetry model uses. Looking a header up in the
        mapping produced an empty cell for every column.
        """
        self.widget.set_telemetry(_telemetry())
        self.assertEqual(self.widget.power_table.rowCount(), 1)
        cells = self._cells(self.widget.power_table)
        self.assertTrue(all(cells), f"empty electrical row: {cells}")

    def test_the_electrical_row_names_the_network(self):
        """The first cell names the observed network."""
        self.widget.set_telemetry(_telemetry())
        self.assertEqual(self._cells(self.widget.power_table)[0], "Network 1")

    def test_the_electrical_row_shows_the_satisfaction(self):
        """The satisfaction is shown, not blank."""
        self.widget.set_telemetry(_telemetry(satisfaction=0.9))
        cells = self._cells(self.widget.power_table)
        self.assertIn("90.0%", cells)

    def test_the_electrical_row_shows_the_headroom(self):
        """The headroom is shown, not blank."""
        self.widget.set_telemetry(
            _telemetry(production=1000, consumption=900))
        cells = self._cells(self.widget.power_table)
        self.assertTrue(any("headroom" not in cell.lower() for cell in cells))

    def test_every_electrical_column_is_filled(self):
        """No column of the electrical table is left empty."""
        self.widget.set_telemetry(_telemetry())
        for column in range(self.widget.power_table.columnCount()):
            item = self.widget.power_table.item(0, column)
            self.assertIsNotNone(item)
            self.assertTrue(item.text().strip(),
                            f"column {column} is empty")

    def test_the_column_keys_match_the_display_mapping(self):
        """The column keys are the names the display mapping uses."""
        from qt_telemetry import network_display

        display = network_display(self.widget.set_telemetry(
            _telemetry()) or self.widget.model.networks[0])
        for key in qt_telemetry_widget.POWER_KEYS:
            self.assertIn(key, display)

    def test_a_missing_payload_shows_no_rows(self):
        """A missing observation must not become a table of zeroes."""
        self.widget.set_telemetry(None)
        self.assertEqual(self.widget.flow_table.rowCount(), 0)
        self.assertEqual(self.widget.power_table.rowCount(), 0)

    def test_the_candidates_are_shown(self):
        """The observed candidate is named."""
        self.widget.set_telemetry(_telemetry(satisfaction=0.9))
        text = self.widget.candidates.toPlainText()
        self.assertIn("power network 1", text)

    def test_no_candidate_says_so(self):
        """The panel says plainly when no candidate was found."""
        self.widget.set_telemetry(None)
        text = self.widget.candidates.toPlainText()
        self.assertIn("No telemetry-backed bottleneck candidate", text)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class TelemetryChartTests(unittest.TestCase):
    """The workspace draws the historical charts of the observed series."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_telemetry_widget.TelemetryWidget(
            qt_telemetry_widget.ROLE_PRODUCTION)
        self.electrical = qt_telemetry_widget.TelemetryWidget(
            qt_telemetry_widget.ROLE_ELECTRICAL)

    def tearDown(self):
        for widget in (self.widget, self.electrical):
            widget.close()
            widget.deleteLater()

    def test_the_production_workspace_draws_a_chart(self):
        """An observed material produces a chart."""
        self.widget.set_telemetry(_telemetry())
        self.assertGreaterEqual(len(self.widget.charts), 1)

    def test_the_chart_draws_the_observed_rate(self):
        """The chart shows the observed per-minute rate.

        The history stores the observed per-minute rate. The per-second
        figure is the verified estimate the model derives, so it is not
        charted as if it had been observed.
        """
        self.widget.set_telemetry(_telemetry())
        values = self.widget.chart_values(0)
        self.assertTrue(values)
        self.assertAlmostEqual(values[-1], 10.0)

    def test_the_chart_grows_with_the_observations(self):
        """Each observation adds exactly one sample."""
        self.widget.set_telemetry(_telemetry(tick=1))
        self.widget.set_telemetry(_telemetry(tick=2))
        self.widget.set_telemetry(_telemetry(tick=3))
        self.assertEqual(len(self.widget.chart_values(0)), 3)

    def test_the_history_is_bounded(self):
        """The chart keeps at most the configured number of samples."""
        for tick in range(1, 400):
            self.widget.set_telemetry(_telemetry(tick=tick))
        self.assertLessEqual(
            len(self.widget.chart_values(0)),
            self.widget.history.maximum_points)

    def test_an_invalid_payload_contributes_no_sample(self):
        """A payload that does not validate adds nothing to the chart."""
        self.widget.set_telemetry(_telemetry())
        before = len(self.widget.chart_values(0))
        self.widget.set_telemetry({"production": "not a payload"})
        self.assertEqual(len(self.widget.chart_values(0)), before)

    def test_the_selector_offers_the_observed_material(self):
        """Only a material that was observed is offered."""
        self.widget.set_telemetry(_telemetry())
        names = [self.widget.selector.itemText(i)
                 for i in range(self.widget.selector.count())]
        self.assertIn("iron-plate", names)

    def test_the_selector_is_empty_without_observations(self):
        """An empty selector offers nothing, so no invented subject."""
        self.widget.set_telemetry(None)
        self.assertEqual(self.widget.selector.count(), 0)
        self.assertEqual(len(self.widget.charts), 0)

    def test_the_electrical_workspace_draws_the_network_charts(self):
        """The electrical workspace draws generation, consumption and
        satisfaction for the selected network."""
        self.electrical.set_telemetry(_telemetry())
        self.assertEqual(len(self.electrical.charts), 3)
        names = [self.electrical.selector.itemText(i)
                 for i in range(self.electrical.selector.count())]
        self.assertIn("network-1", names)

    def test_the_electrical_chart_shows_the_observed_watts(self):
        """The generation chart shows the observed watts.

        The observer reports 1000 J/tick, which is 60000 W at 60 ticks per
        second. The chart must show the observed figure, not the raw
        joules.
        """
        self.electrical.set_telemetry(_telemetry(production=1000))
        values = self.electrical.chart_values(0)
        self.assertTrue(values)
        self.assertAlmostEqual(values[-1], 60000.0)

    def test_the_two_workspaces_keep_separate_histories(self):
        """The material chart and the network chart never mix."""
        self.widget.set_telemetry(_telemetry())
        self.electrical.set_telemetry(_telemetry())
        self.assertIsNot(self.widget.history, self.electrical.history)
        self.assertEqual(len(self.widget.chart_values(0)), 1)
        self.assertEqual(len(self.electrical.chart_values(0)), 1)

    def test_a_reconnect_does_not_join_two_games_into_one_line(self):
        """A tick that went backwards clears the history."""
        self.widget.set_telemetry(_telemetry(tick=100))
        self.widget.set_telemetry(_telemetry(tick=200))
        self.widget.set_telemetry(_telemetry(tick=50))
        self.assertEqual(len(self.widget.chart_values(0)), 1)
        self.assertGreaterEqual(self.widget.history.resets, 1)

    def test_a_long_gap_clears_the_history(self):
        """A gap longer than the allowed gap breaks the line."""
        self.widget.set_telemetry(_telemetry(tick=1), at=1000.0)
        self.widget.set_telemetry(_telemetry(tick=2), at=1000.0 + 3600.0)
        self.assertEqual(len(self.widget.chart_values(0)), 1)

    def test_the_chart_survives_a_paint(self):
        """The chart really paints the observed values."""
        self.widget.set_telemetry(_telemetry())
        self.widget.resize(900, 600)
        self.widget.show()
        self.app.processEvents()
        self.assertTrue(self.widget.charts)
        self.assertGreater(self.widget.charts[0].paint_count, 0)
        self.assertEqual(len(self.widget.chart_values(0)), 1)

    def test_an_unknown_role_is_refused(self):
        """A mistyped role is an error, not a silent default."""
        with self.assertRaises(ValueError):
            qt_telemetry_widget.TelemetryWidget("nonsense")


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class TelemetrySurfaceTests(unittest.TestCase):
    """The panel names the surface the numbers describe."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_telemetry_widget.TelemetryWidget(
            qt_telemetry_widget.ROLE_PRODUCTION)

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def test_the_observed_surface_is_shown(self):
        """The surface is named so the user knows what the numbers mean."""
        self.widget.set_telemetry(_telemetry(surface="vulcanus"))
        self.assertIn("vulcanus", self.widget.surface.text())

    def test_an_unobserved_surface_is_not_claimed(self):
        """A payload without a surface never names a surface.

        The panel says the surface was not reported, so the user is not
        left guessing which world the numbers describe.
        """
        self.widget.set_telemetry(_telemetry())
        text = self.widget.surface.text()
        self.assertNotIn("nauvis", text)
        self.assertNotIn("vulcanus", text)
        self.assertIn("not reported", text)

    def test_a_surface_change_clears_the_chart_line(self):
        """The chart never joins two surfaces into one line."""
        self.widget.set_telemetry(_telemetry(tick=1, surface="nauvis"))
        self.widget.set_telemetry(_telemetry(tick=2, surface="nauvis"))
        self.assertEqual(len(self.widget.chart_values(0)), 2)
        self.widget.set_telemetry(_telemetry(tick=3, surface="vulcanus"))
        self.assertEqual(len(self.widget.chart_values(0)), 1)
        self.assertIn("vulcanus", self.widget.surface.text())

    def test_the_chart_still_draws_after_a_surface_change(self):
        """The new surface's samples are really drawn."""
        self.widget.set_telemetry(_telemetry(tick=1, surface="nauvis"))
        self.widget.set_telemetry(_telemetry(tick=2, surface="vulcanus"))
        self.widget.resize(900, 600)
        self.widget.show()
        self.app.processEvents()
        self.assertGreater(self.widget.charts[0].paint_count, 0)
        self.assertEqual(len(self.widget.chart_values(0)), 1)


if __name__ == "__main__":
    unittest.main()
