"""Regression tests for the native Qt telemetry charts.

The **geometry** tests need no optional dependency: :mod:`qt_chart_geometry`
holds the pure part of the chart and contains no Qt import, so those tests
run everywhere.

The **widget** tests need PySide6. They run on the **offscreen** platform
plugin so they need no display server, and they skip cleanly when PySide6
is not installed, so the offline suite still passes without the optional UI
dependency.

The tests prove the properties that make a chart trustworthy:

* it draws **exactly** the observed samples and never an extra point;
* it never invents a value for an observation that did not arrive;
* it stays bounded;
* it does not repaint when nothing changed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qt_chart_geometry import (  # noqa: E402
    ChartSpec,
    axis_decimals,
    axis_ticks,
    build_geometry,
    format_axis_tick,
    format_axis_time,
    format_axis_value,
    layout_geometry,
)
from qt_telemetry_history import HistoryPoint  # noqa: E402

try:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication

    import qt_chart

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


def _history(values, stamps=None, unit="units/min", name="iron-plate output"):
    """Return one observed history point."""
    if stamps is None:
        stamps = [float(index) for index in range(len(values))]
    return HistoryPoint(name=name, unit=unit, values=list(values),
                        stamps=list(stamps))


class ChartGeometryTests(unittest.TestCase):
    """The geometry is computed from the observed samples only."""

    def test_an_empty_history_has_no_geometry(self):
        """A history without samples produces an empty geometry."""
        geometry = build_geometry(_history([]))
        self.assertTrue(geometry.empty)
        self.assertEqual(geometry.values, ())

    def test_the_geometry_holds_every_observed_value(self):
        """The geometry keeps exactly the observed values."""
        geometry = build_geometry(_history([1.0, 2.0, 3.0]))
        self.assertFalse(geometry.empty)
        self.assertEqual(geometry.values, (1.0, 2.0, 3.0))

    def test_a_non_finite_value_is_not_charted(self):
        """A NaN never becomes a drawn point."""
        geometry = build_geometry(
            _history([1.0, float("nan"), 3.0]))
        self.assertEqual(len(geometry.values), 2)

    def test_the_scale_starts_at_zero_for_positive_values(self):
        """A positive series is scaled from zero, not from its minimum.

        A chart that starts at the minimum would exaggerate a small
        change, which misrepresents what was observed.
        """
        geometry = build_geometry(_history([10.0, 11.0]))
        self.assertEqual(geometry.minimum, 0.0)
        self.assertEqual(geometry.maximum, 11.0)

    def test_a_negative_series_keeps_its_real_range(self):
        """A negative value is charted against the real range."""
        geometry = build_geometry(_history([-5.0, 2.0]))
        self.assertEqual(geometry.minimum, -5.0)
        self.assertEqual(geometry.maximum, 2.0)

    def test_a_flat_series_still_has_a_scale(self):
        """A flat series gets a scale, so the line is visible."""
        geometry = build_geometry(_history([4.0, 4.0]))
        self.assertGreater(geometry.maximum, geometry.minimum)

    def test_the_axis_ticks_include_the_exact_range(self):
        """The grid lines show the real minimum and maximum."""
        geometry = build_geometry(_history([0.0, 7.5]))
        ticks = axis_ticks(geometry)
        self.assertEqual(ticks[0], 0.0)
        self.assertEqual(ticks[-1], 7.5)


class ChartLayoutTests(unittest.TestCase):
    """The layout maps the observed samples into the plot area."""

    def test_the_layout_draws_exactly_the_observed_points(self):
        """No point is added and none is lost."""
        geometry = build_geometry(_history([1.0, 2.0, 3.0]))
        _scale, points = layout_geometry(
            geometry, width=100.0, height=50.0)
        self.assertEqual(len(points), 3)
        self.assertEqual([p.value for p in points], [1.0, 2.0, 3.0])

    def test_an_empty_geometry_lays_out_nothing(self):
        """An empty geometry draws no points at all."""
        geometry = build_geometry(_history([]))
        _scale, points = layout_geometry(
            geometry, width=100.0, height=50.0)
        self.assertEqual(points, ())

    def test_the_first_point_starts_at_the_left_edge(self):
        """The first observed sample is at the left of the plot."""
        geometry = build_geometry(_history([1.0, 2.0]))
        _scale, points = layout_geometry(
            geometry, width=100.0, height=50.0)
        self.assertAlmostEqual(points[0].x, 0.0)
        self.assertAlmostEqual(points[-1].x, 100.0)

    def test_the_highest_value_is_at_the_top(self):
        """The maximum observed value sits at the top of the plot.

        The scale starts at zero for a positive series, so the position of
        a value follows the real ratio against the observed range.
        """
        geometry = build_geometry(_history([1.0, 9.0, 4.0]))
        _scale, points = layout_geometry(
            geometry, width=100.0, height=50.0)
        self.assertAlmostEqual(points[1].y, 0.0)
        self.assertAlmostEqual(points[0].y, 50.0 * (1.0 - 1.0 / 9.0))
        self.assertAlmostEqual(points[2].y, 50.0 * (1.0 - 4.0 / 9.0))

    def test_a_single_sample_is_drawn_in_the_middle(self):
        """One observed sample has no width, so it sits in the middle."""
        geometry = build_geometry(_history([1.0]))
        _scale, points = layout_geometry(
            geometry, width=100.0, height=50.0)
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0].x, 50.0)


class AxisFormattingTests(unittest.TestCase):
    """The axes read in the unit of the observation."""

    def test_a_short_window_reads_in_seconds(self):
        """A window under a minute and a half reads in seconds."""
        self.assertEqual(format_axis_time(30.0, 60.0), "30s")

    def test_a_medium_window_reads_in_minutes(self):
        """A window of minutes reads in minutes."""
        self.assertEqual(format_axis_time(120.0, 600.0), "2.0m")

    def test_a_long_window_reads_in_hours(self):
        """A window of hours reads in hours."""
        self.assertEqual(format_axis_time(7200.0, 14400.0), "2.0h")

    def test_a_zero_span_reads_as_zero(self):
        """A chart without a span does not claim a time."""
        self.assertEqual(format_axis_time(0.0, 0.0), "0s")

    def test_the_time_axis_reads_the_elapsed_time(self):
        """The label is the elapsed time, not the absolute moment.

        An absolute reading would change the whole axis when the window
        slid, and the user would have to do arithmetic to know how long
        ago something happened.
        """
        self.assertEqual(format_axis_time(5000.0, 120.0, elapsed=0.0), "0s")
        self.assertEqual(format_axis_time(5060.0, 120.0, elapsed=60.0), "60s")

    def test_a_two_minute_axis_reads_in_seconds(self):
        """The unit follows the largest label, not the span alone.

        A chart that covers two minutes reads "0s" to "120s", which is
        easier to follow than "0.0m" to "2.0m".
        """
        self.assertEqual(format_axis_time(5060.0, 120.0, elapsed=60.0), "60s")
        self.assertEqual(format_axis_time(5120.0, 120.0, elapsed=120.0),
                         "120s")

    def test_a_ratio_is_shown_as_a_percentage(self):
        """A satisfaction ratio reads as a percentage."""
        self.assertEqual(format_axis_value(0.9, "ratio"), "90%")

    def test_watts_are_shown_in_kilowatts(self):
        """A large power figure reads in kilowatts."""
        self.assertEqual(format_axis_value(1500.0, "W"), "1.5kW")

    def test_a_rate_is_shown_in_thousands(self):
        """A large rate reads in thousands."""
        self.assertEqual(format_axis_value(2500.0, "units/min"),
                         "2.5k")


class AxisPrecisionTests(unittest.TestCase):
    """The grid lines read with the precision the step needs."""

    def test_a_whole_step_needs_no_decimals(self):
        """A step of one or more reads as a whole number."""
        ticks = (0.0, 2.0, 4.0, 6.0)
        self.assertEqual(axis_decimals(ticks), 0)

    def test_a_fractional_step_keeps_its_decimals(self):
        """A step of a third keeps one decimal.

        Without this the ticks 0, 3.33, 6.67 and 10 would print as 0, 3,
        7 and 10, which reads as a different scale than the one drawn.
        """
        geometry = build_geometry(_history([0.0, 10.0]))
        ticks = axis_ticks(geometry)
        decimals = axis_decimals(ticks)
        self.assertEqual(decimals, 1)
        labels = [format_axis_tick(tick, "units/min", decimals)
                  for tick in ticks]
        self.assertEqual(labels[0], "0.0")
        self.assertEqual(labels[-1], "10.0")
        self.assertNotEqual(labels[1], labels[2])

    def test_a_small_step_keeps_a_decimal(self):
        """A step of a tenth keeps one decimal to stay distinct."""
        geometry = build_geometry(_history([0.0, 0.3]))
        decimals = axis_decimals(axis_ticks(geometry))
        self.assertGreaterEqual(decimals, 1)

    def test_a_single_tick_needs_no_decimals(self):
        """A chart with one grid line has no step to measure."""
        self.assertEqual(axis_decimals((1.0,)), 0)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class ChartWidgetTests(unittest.TestCase):
    """The widget paints the observed samples."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_chart.TelemetryChartWidget()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def _spec(self, values, **kwargs):
        """Return one chart spec."""
        return qt_chart.ChartSpec(
            key=kwargs.pop("key", "series"),
            title=kwargs.pop("title", "Output"),
            unit=kwargs.pop("unit", "units/min"),
            values=tuple(float(v) for v in values),
            stamps=tuple(float(s) for s in range(len(values))),
            **kwargs)

    def test_an_empty_chart_draws_nothing(self):
        """A chart without samples draws no points."""
        self.widget.set_spec(self._spec([]))
        self.widget.resize(300, 200)
        self.widget.show()
        self.app.processEvents()
        self.assertEqual(self.widget.drawn_points, 0)

    def test_the_chart_draws_every_observed_value(self):
        """The drawn points match the observed values exactly."""
        self.widget.set_spec(self._spec([1.0, 5.0, 3.0]))
        self.widget.resize(300, 200)
        self.widget.show()
        self.app.processEvents()
        self.assertEqual(self.widget.drawn_values(), [1.0, 5.0, 3.0])

    def test_an_unchanged_spec_does_not_schedule_a_repaint(self):
        """A repeated observation does not cost a repaint."""
        spec = self._spec([1.0, 2.0])
        self.assertTrue(self.widget.set_spec(spec))
        self.assertFalse(self.widget.set_spec(spec))

    def test_a_changed_spec_schedules_a_repaint(self):
        """A new observation does schedule a repaint."""
        self.assertTrue(self.widget.set_spec(self._spec([1.0, 2.0])))
        self.assertTrue(self.widget.set_spec(self._spec([1.0, 2.0, 3.0])))

    def test_the_chart_paints_without_error(self):
        """The paint does not raise and the chart really painted."""
        self.widget.set_spec(self._spec([1.0, 4.0, 2.0]))
        self.widget.resize(300, 200)
        self.widget.show()
        self.app.processEvents()
        self.assertGreater(self.widget.paint_count, 0)
        self.assertEqual(self.widget.drawn_points, 3)

    def test_an_unavailable_chart_says_so(self):
        """A chart without an observation says so instead of faking data."""
        self.widget.set_spec(self._spec([], unavailable=True))
        self.widget.resize(300, 200)
        self.widget.show()
        self.app.processEvents()
        self.assertEqual(self.widget.drawn_points, 0)


class ChartSpecSignatureTests(unittest.TestCase):
    """The cache key covers every sample, not only the newest one.

    These tests need no optional dependency: :class:`ChartSpec` is a plain
    dataclass and its signature is pure Python, so the regression is
    proven everywhere, including a machine without PySide6.
    """

    @staticmethod
    def _spec(values, stamps=None, **kwargs):
        """Return one chart spec."""
        if stamps is None:
            stamps = [float(index) for index in range(len(values))]
        return ChartSpec(
            key=kwargs.pop("key", "series"),
            title=kwargs.pop("title", "Output"),
            unit=kwargs.pop("unit", "units/min"),
            values=tuple(float(v) for v in values),
            stamps=tuple(float(s) for s in stamps),
            **kwargs)

    def test_an_unchanged_series_has_the_same_signature(self):
        """A repeated observation keeps the same cache key."""
        self.assertEqual(self._spec([1.0, 5.0, 3.0]).signature(),
                         self._spec([1.0, 5.0, 3.0]).signature())

    def test_a_changed_intermediate_sample_changes_the_signature(self):
        """A corrected older sample must invalidate the cached drawing.

        The sample count and the final sample are unchanged here, so a
        signature built from the final sample alone would report "no
        change" and the chart would keep drawing the wrong line.
        """
        original = self._spec([1.0, 5.0, 3.0])
        corrected = self._spec([1.0, 9.0, 3.0])
        self.assertEqual(len(original.values), len(corrected.values))
        self.assertEqual(original.values[-1], corrected.values[-1])
        self.assertNotEqual(original.signature(), corrected.signature())

    def test_a_changed_first_sample_changes_the_signature(self):
        """The oldest sample is part of the drawing too."""
        self.assertNotEqual(self._spec([1.0, 5.0, 3.0]).signature(),
                            self._spec([2.0, 5.0, 3.0]).signature())

    def test_a_changed_timestamp_changes_the_signature(self):
        """A corrected timestamp changes the horizontal layout."""
        self.assertNotEqual(
            self._spec([1.0, 5.0], stamps=[0.0, 1.0]).signature(),
            self._spec([1.0, 5.0], stamps=[0.0, 2.0]).signature())

    def test_a_changed_colour_changes_the_signature(self):
        """The colour is part of what is drawn."""
        self.assertNotEqual(self._spec([1.0], color="#ffffff").signature(),
                            self._spec([1.0], color="#000000").signature())

    def test_a_changed_stale_flag_changes_the_signature(self):
        """The stale flag changes the drawn colour."""
        self.assertNotEqual(self._spec([1.0], stale=False).signature(),
                            self._spec([1.0], stale=True).signature())

    def test_a_changed_unavailable_flag_changes_the_signature(self):
        """The unavailable flag changes what is drawn instead."""
        self.assertNotEqual(self._spec([1.0], unavailable=False).signature(),
                            self._spec([1.0], unavailable=True).signature())

    def test_swapped_values_and_timestamps_differ(self):
        """Values and timestamps are packed in separate blocks.

        Otherwise a series whose values and timestamps were exchanged
        could collide with the original.
        """
        self.assertNotEqual(
            self._spec([1.0, 2.0], stamps=[10.0, 20.0]).signature(),
            self._spec([10.0, 20.0], stamps=[1.0, 2.0]).signature())

    def test_an_emptied_series_changes_the_signature(self):
        """Losing every sample must invalidate the drawing."""
        self.assertNotEqual(self._spec([1.0, 5.0]).signature(),
                            self._spec([]).signature())


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class ChartRepaintRegressionTests(unittest.TestCase):
    """A corrected observation really repaints the chart."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_chart.TelemetryChartWidget()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def _spec(self, values):
        """Return one chart spec."""
        return ChartSpec(
            key="series", title="Output", unit="units/min",
            values=tuple(float(v) for v in values),
            stamps=tuple(float(s) for s in range(len(values))))

    def test_a_corrected_intermediate_sample_repaints_the_chart(self):
        """The graph shows the corrected sample after the correction.

        This is the acceptance case: the number of samples and the final
        sample are unchanged, so only a cache key that covers every
        sample can notice the correction.
        """
        self.assertTrue(self.widget.set_spec(self._spec([1.0, 5.0, 3.0])))
        self.widget.resize(300, 200)
        self.widget.show()
        self.app.processEvents()
        self.assertEqual(self.widget.drawn_values(), [1.0, 5.0, 3.0])

        self.assertTrue(self.widget.set_spec(self._spec([1.0, 9.0, 3.0])))
        self.app.processEvents()
        self.assertEqual(self.widget.drawn_values(), [1.0, 9.0, 3.0])

    def test_an_identical_series_does_not_repaint(self):
        """An unchanged series still costs no repaint."""
        spec = self._spec([1.0, 5.0, 3.0])
        self.assertTrue(self.widget.set_spec(spec))
        self.assertFalse(self.widget.set_spec(self._spec([1.0, 5.0, 3.0])))

    def test_a_correction_is_painted_not_only_requested(self):
        """The correction reaches the screen, not just the widget state."""
        self.widget.set_spec(self._spec([1.0, 5.0, 3.0]))
        self.widget.resize(300, 200)
        self.widget.show()
        self.app.processEvents()
        painted_before = self.widget.paint_count

        self.widget.set_spec(self._spec([1.0, 9.0, 3.0]))
        self.app.processEvents()
        self.assertGreater(self.widget.paint_count, painted_before)
        self.assertEqual(self.widget.drawn_values(), [1.0, 9.0, 3.0])


if __name__ == "__main__":
    unittest.main()
