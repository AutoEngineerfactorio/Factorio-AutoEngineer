"""Regression tests for the bounded telemetry history.

The history is the data behind the production and electrical charts. These
tests check that it:

* keeps the **observed** rates and nothing invented;
* stays **bounded**;
* names its **units** explicitly;
* clears itself on a telemetry **reset** and on a long **reconnection**
  gap, so a chart never joins two different games into one line.

These tests import no Qt module: the history is pure logic, and it must
stay verifiable offline.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from qt_telemetry import build_model  # noqa: E402
from qt_telemetry_history import (  # noqa: E402
    FLOW_INPUT,
    FLOW_OUTPUT,
    POWER_CONSUMPTION,
    POWER_GENERATION,
    POWER_SATISFACTION,
    TelemetryHistory,
)


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
        "candidate_bucket_count": max(1, (count + cap - 1) // cap),
        "partial": count > cap,
        "series": series,
    }


def _telemetry(tick=123, satisfaction=0.9, production=1000, consumption=900,
               output=10.0, item="iron-plate", surface=None):
    """Return one validated telemetry payload.

    The ``surface`` is a **sibling** of the validated envelope, exactly as
    the mod reports it. It is left out by default, so the ordinary tests
    describe a payload that carries no surface at all.
    """
    payload = {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": "partial",
            "reason": "Only one bounded prototype bucket is sampled",
            "items": _group(128, [{
                "name": item,
                "input": [2.0] * 60,
                "output": [output] * 60,
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


class TelemetryHistoryTests(unittest.TestCase):
    """The history records what was observed and keeps itself bounded."""

    def test_an_empty_history_has_no_charts(self):
        history = TelemetryHistory()
        self.assertEqual(history.series_keys(), ())
        self.assertEqual(history.production_charts, [])
        self.assertEqual(history.electrical_charts, [])

    def test_a_payload_creates_the_production_chart(self):
        """The observed output rate is charted."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        charts = history.production_charts
        self.assertTrue(charts)
        output = charts[0]
        self.assertEqual(output.name, "iron-plate output")
        self.assertEqual(output.values, [10.0])

    def test_the_input_and_output_charts_are_told_apart(self):
        """The two charts of one material have different names."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        names = {chart.name for chart in history.production_charts}
        self.assertIn("iron-plate output", names)
        self.assertIn("iron-plate input", names)

    def test_a_payload_creates_the_electrical_chart(self):
        """The observed generation and consumption are charted."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        charts = history.electrical_charts
        self.assertTrue(charts)
        keys = history.series_keys()
        self.assertTrue(any(key.startswith(POWER_GENERATION) for key in keys))
        self.assertTrue(any(key.startswith(POWER_CONSUMPTION) for key in keys))
        self.assertTrue(any(key.startswith(POWER_SATISFACTION) for key in keys))

    def test_the_units_are_explicit(self):
        """Every chart names the unit its values are in."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        for chart in history.production_charts + history.electrical_charts:
            self.assertTrue(chart.unit, chart.name)
        output = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(output.unit, "units/min")
        watts = history.chart(f"{POWER_GENERATION}:network-1")
        self.assertEqual(watts.unit, "W")

    def test_the_timestamps_are_explicit(self):
        """Every sample carries the moment it was observed."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        history.observe(_telemetry(tick=124), at=102.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(chart.stamps, [100.0, 102.0])
        self.assertEqual(chart.latest_at, 102.0)
        self.assertEqual(chart.span_seconds(), 2.0)

    def test_the_ticks_are_kept(self):
        """Every sample carries the game tick it was observed at."""
        history = TelemetryHistory()
        history.observe(_telemetry(tick=123), at=100.0)
        history.observe(_telemetry(tick=124), at=102.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(chart.ticks, [123, 124])

    def test_the_per_minute_rate_is_the_observed_one(self):
        """The chart carries the observed per-minute rate."""
        history = TelemetryHistory()
        history.observe(_telemetry(output=42.0), at=100.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(chart.values, [42.0])

    def test_the_input_rate_is_charted_separately(self):
        """The input and the output are separate charts."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        self.assertEqual(history.chart(f"{FLOW_INPUT}:iron-plate").values, [2.0])
        self.assertEqual(history.chart(f"{FLOW_OUTPUT}:iron-plate").values, [10.0])

    def test_several_observations_accumulate(self):
        """The history grows with every observation."""
        history = TelemetryHistory()
        for index in range(5):
            history.observe(_telemetry(tick=123 + index), at=100.0 + index)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 5)

    def test_the_history_is_bounded_by_the_point_limit(self):
        """The history never grows past its point limit."""
        history = TelemetryHistory(maximum_points=10)
        for index in range(50):
            history.observe(_telemetry(tick=123 + index), at=100.0 + index)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 10)

    def test_the_history_is_bounded_by_the_window(self):
        """The samples that fell out of the window are dropped."""
        history = TelemetryHistory(window_minutes=1.0, maximum_points=1000)
        history.observe(_telemetry(tick=123), at=0.0)
        history.observe(_telemetry(tick=124), at=10.0)
        # At t=200 the one-minute window only reaches back to t=140, so
        # both earlier samples are out of the window.
        history.observe(_telemetry(tick=125), at=200.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(chart.values, [10.0])
        self.assertEqual(chart.stamps, [200.0])

    def test_a_sample_inside_the_window_is_kept(self):
        """A sample that is still inside the window survives."""
        history = TelemetryHistory(window_minutes=1.0, maximum_points=1000)
        history.observe(_telemetry(tick=123), at=0.0)
        history.observe(_telemetry(tick=124), at=30.0)
        history.observe(_telemetry(tick=125), at=50.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        # The window reaches back to t=-10, so every sample is inside it.
        self.assertEqual(chart.stamps, [0.0, 30.0, 50.0])

    def test_the_newest_sample_survives_even_outside_the_window(self):
        """A chart always keeps its most recent sample."""
        history = TelemetryHistory(window_minutes=1.0, maximum_points=1000)
        history.observe(_telemetry(tick=123), at=0.0)
        history.observe(_telemetry(tick=124), at=5000.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 1)
        self.assertEqual(chart.stamps, [5000.0])

    def test_the_window_is_configurable(self):
        """The window can be changed."""
        history = TelemetryHistory()
        history.set_window(5.0)
        self.assertEqual(history.window_minutes, 5.0)
        with self.assertRaises(ValueError):
            history.set_window(0)

    def test_an_invalid_payload_is_rejected(self):
        """A payload that does not validate contributes nothing."""
        history = TelemetryHistory()
        history.observe({"schema": 9}, at=100.0)
        self.assertEqual(history.series_keys(), ())
        self.assertEqual(history.rejections, 1)

    def test_a_missing_payload_is_rejected(self):
        """A missing payload contributes nothing."""
        history = TelemetryHistory()
        history.observe(None, at=100.0)
        self.assertEqual(history.series_keys(), ())
        self.assertEqual(history.rejections, 1)

    def test_a_telemetry_reset_clears_the_history(self):
        """A tick that went backwards clears the history.

        Joining two different games into one line would misrepresent what
        happened, so the history restarts instead.
        """
        history = TelemetryHistory()
        history.observe(_telemetry(tick=500), at=100.0)
        history.observe(_telemetry(tick=501), at=102.0)
        self.assertEqual(len(history.chart(f"{FLOW_OUTPUT}:iron-plate").values), 2)
        history.observe(_telemetry(tick=10), at=104.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 1)
        self.assertEqual(history.resets, 1)

    def test_a_long_gap_clears_the_history(self):
        """A long reconnection gap clears the history.

        A straight line across a gap would claim a continuity that was
        never observed.
        """
        history = TelemetryHistory(maximum_gap_seconds=30.0)
        history.observe(_telemetry(tick=500), at=100.0)
        history.observe(_telemetry(tick=501), at=102.0)
        history.observe(_telemetry(tick=502), at=200.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 1)
        self.assertEqual(chart.stamps, [200.0])

    def test_a_short_gap_keeps_the_history(self):
        """A short gap does not clear the history."""
        history = TelemetryHistory(maximum_gap_seconds=30.0)
        history.observe(_telemetry(tick=500), at=100.0)
        history.observe(_telemetry(tick=501), at=120.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 2)

    def test_a_reconnection_after_a_reset_keeps_the_new_data(self):
        """After a reset the new observation is charted normally."""
        history = TelemetryHistory()
        history.observe(_telemetry(tick=500), at=100.0)
        history.observe(_telemetry(tick=10), at=102.0)
        history.observe(_telemetry(tick=11), at=104.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(chart.ticks, [10, 11])

    def test_several_networks_get_separate_charts(self):
        """Each electrical network gets its own charts."""
        history = TelemetryHistory()
        payload = _telemetry()
        payload["power"]["networks"].append({
            "network_id": 2,
            "tick": 123,
            "maximum_production": 500,
            "maximum_consumption": 400,
            "consumption_satisfaction": 1.0,
            "production_satisfaction": 1,
            "accumulator_energy": 0,
            "accumulator_capacity": 0,
        })
        history.observe(payload, at=100.0)
        keys = history.series_keys()
        self.assertTrue(any("network-1" in key for key in keys))
        self.assertTrue(any("network-2" in key for key in keys))

    def test_the_statistics_are_bounded(self):
        """The summary reports what the history holds."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        stats = history.stats()
        self.assertEqual(stats["series"], len(history.series_keys()))
        self.assertGreater(stats["points"], 0)
        self.assertEqual(stats["window_minutes"], history.window_minutes)

    def test_clearing_drops_everything(self):
        """Clearing drops every sample."""
        history = TelemetryHistory()
        history.observe(_telemetry(), at=100.0)
        history.clear()
        self.assertEqual(history.series_keys(), ())
        self.assertEqual(history.stats()["points"], 0)

    def test_the_module_holds_no_transport(self):
        """The history must not reach the game by itself."""
        import ast

        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_telemetry_history.py")
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

    def test_the_module_imports_no_qt(self):
        """The history must stay verifiable without a display server."""
        import ast

        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_telemetry_history.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("PySide6", imported)


class SurfaceAwareHistoryTests(unittest.TestCase):
    """A surface change must not join two surfaces into one line.

    The game tick keeps rising when the player changes surface, so the
    tick alone cannot detect the change. The history therefore watches
    the observed surface as well.
    """

    def test_the_model_reports_the_observed_surface(self):
        """The model carries the surface the observation came from."""
        model = build_model(_telemetry(surface="vulcanus"))
        self.assertEqual(model.surface, "vulcanus")

    def test_a_payload_without_a_surface_reports_no_surface(self):
        """A missing surface is empty, not "nauvis".

        An empty surface means "the surface was not reported", so it
        never triggers a reset on its own.
        """
        model = build_model(_telemetry())
        self.assertEqual(model.surface, "")

    def test_a_malformed_surface_is_ignored(self):
        """A surface that is not a usable name is not reported."""
        self.assertEqual(build_model(_telemetry(surface=12345)).surface, "")
        self.assertEqual(build_model(_telemetry(surface="")).surface, "")

    def test_a_surface_change_resets_the_history(self):
        """The old surface's samples are dropped, not joined."""
        history = TelemetryHistory()
        history.observe(_telemetry(tick=500, surface="nauvis"), at=100.0)
        history.observe(_telemetry(tick=501, surface="nauvis"), at=102.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 2)

        # The tick keeps rising, so only the surface reveals the change.
        history.observe(_telemetry(tick=502, surface="vulcanus"), at=104.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 1)
        self.assertEqual(history.resets, 1)

    def test_the_same_surface_keeps_the_history(self):
        """The same surface is a continuation, not a reset."""
        history = TelemetryHistory()
        history.observe(_telemetry(tick=500, surface="nauvis"), at=100.0)
        history.observe(_telemetry(tick=501, surface="nauvis"), at=102.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 2)
        self.assertEqual(history.resets, 0)

    def test_a_payload_without_a_surface_never_resets(self):
        """An unreported surface must not clear a valid history."""
        history = TelemetryHistory()
        history.observe(_telemetry(tick=500, surface="nauvis"), at=100.0)
        history.observe(_telemetry(tick=501), at=102.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 2)
        self.assertEqual(history.resets, 0)

    def test_the_history_forgets_the_surface_when_cleared(self):
        """Clearing drops the remembered surface too."""
        history = TelemetryHistory()
        history.observe(_telemetry(tick=500, surface="nauvis"), at=100.0)
        history.clear()
        # A payload from another surface must not be treated as a change
        # after the history was cleared.
        history.observe(_telemetry(tick=501, surface="vulcanus"), at=102.0)
        chart = history.chart(f"{FLOW_OUTPUT}:iron-plate")
        self.assertEqual(len(chart.values), 1)
        self.assertEqual(history.resets, 0)


class ConfigurableRetentionTests(unittest.TestCase):
    """The retention comes from the settings, not from a constant."""

    def test_the_default_point_limit_is_bounded(self):
        history = TelemetryHistory()
        self.assertGreaterEqual(history.maximum_points, 1)
        self.assertLessEqual(history.maximum_points, 100000)

    def test_the_configured_retention_is_used(self):
        import qt_telemetry_history as module

        original = module._configured_retention
        module._configured_retention = lambda: (5.0, 42)
        try:
            history = TelemetryHistory()
            self.assertEqual(history.maximum_points, 42)
            self.assertEqual(history.window_minutes, 5.0)
        finally:
            module._configured_retention = original

    def test_an_explicit_retention_still_wins(self):
        history = TelemetryHistory(maximum_points=7)
        self.assertEqual(history.maximum_points, 7)

    def test_the_configured_retention_is_validated(self):
        with self.assertRaises(ValueError):
            TelemetryHistory(maximum_points=0)
        with self.assertRaises(ValueError):
            TelemetryHistory(window_minutes=0)


class HistoryProfileIsolationTests(unittest.TestCase):
    """A history belongs to one profile and one mod configuration."""

    def test_a_different_profile_drops_the_samples(self):
        from cache_context import CacheContext

        history = TelemetryHistory(context=CacheContext("p1", "2.1.23", "fp", "n", "f"))
        history.observe(_telemetry(), at=100.0)
        dropped = history.set_context(
            CacheContext("p2", "2.1.23", "fp", "n", "f"))
        self.assertTrue(dropped)
        self.assertEqual(history.series_keys(), ())

    def test_a_different_mod_fingerprint_drops_the_samples(self):
        from cache_context import CacheContext

        history = TelemetryHistory(context=CacheContext("p1", "2.1.23", "fp1", "n", "f"))
        history.observe(_telemetry(), at=100.0)
        dropped = history.set_context(
            CacheContext("p1", "2.1.23", "fp2", "n", "f"))
        self.assertTrue(dropped)
        self.assertEqual(history.series_keys(), ())

    def test_the_same_context_keeps_the_samples(self):
        from cache_context import CacheContext

        context = CacheContext("p1", "2.1.23", "fp", "n", "f")
        history = TelemetryHistory(context=context)
        history.observe(_telemetry(), at=100.0)
        dropped = history.set_context(context)
        self.assertFalse(dropped)
        self.assertTrue(history.series_keys())

    def test_the_context_is_reported(self):
        from cache_context import CacheContext

        context = CacheContext("p1", "2.1.23", "fp", "n", "f")
        history = TelemetryHistory(context=context)
        self.assertIs(history.context, context)


if __name__ == "__main__":
    unittest.main()
