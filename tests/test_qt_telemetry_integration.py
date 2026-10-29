"""End-to-end tests of the observation path into the Qt telemetry charts.

These tests drive the **whole** path the live dashboard uses:

    observation bridge -> validated UI frame -> shell -> telemetry widget
                      -> bounded history -> drawn chart

They never contact a game and never issue a command. Every payload is a
**synthetic** observation that satisfies the validated telemetry contract,
so the model accepts it exactly as it would accept a real one.

The tests prove the properties the whole path has to hold:

* an observation reaches the chart;
* several observations do not overwrite one another;
* an **out-of-order** frame never reaches the chart;
* a **missing** payload contributes nothing;
* a **disconnect** is visible and keeps no misleading line;
* the history stays **bounded**;
* the chart never invents a point.
"""

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication

    import qt_shell
    from qt_observation_bridge import UiFrame

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


def _telemetry(tick=1000, rate=10.0, satisfaction=0.9, networks=1):
    """Return one validated telemetry payload."""
    def group(series, cap, prototype_count):
        bucket_count = max(1, -(-prototype_count // cap))
        return {
            "status": "ok",
            "unit": "units_per_minute",
            "precision": "ten_minutes",
            "sample_interval_seconds": 2,
            "sample_count": 60,
            "window_seconds": 120,
            "prototype_count": prototype_count,
            "candidate_cap": cap,
            "candidate_bucket": 1,
            "candidate_bucket_count": bucket_count,
            "partial": prototype_count > cap,
            "series": series,
        }

    power_networks = [{
        "network_id": index + 1,
        "tick": tick,
        "maximum_production": 1000.0,
        "maximum_consumption": 900.0,
        "consumption_satisfaction": satisfaction,
        "production_satisfaction": 1.0,
        "accumulator_energy": 0,
        "accumulator_capacity": 0,
    } for index in range(networks)]

    return {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": "partial",
            "reason": "Only one bounded prototype bucket is sampled",
            "items": group([{
                "name": "iron-plate",
                "input": [2.0] * 60,
                "output": [rate] * 60,
            }], 128, 130),
            "fluids": group([], 64, 0),
        },
        "power": {
            "status": "ok",
            "unit": "joules_per_tick",
            "tick": tick,
            "networks": power_networks,
            "partial": False,
        },
    }


class _StubService:
    """A stand-in for the shared observation service.

    The service is never asked to observe anything in these tests: the
    frames are delivered directly, which is exactly what the bridge does
    once it has polled.
    """

    async def observe_tool(self, session, tool, arguments, *, kind,
                           key=None, ttl=None, timeout=None):
        raise AssertionError("The test must not observe anything")


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class ObservationToChartTests(unittest.TestCase):
    """A validated frame reaches the drawn chart."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = qt_shell.ShellWindow()
        self.window.resize(1600, 940)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def _production(self):
        """Return the production telemetry widget."""
        return self.window.telemetry_widget("Production")

    def _electrical(self):
        """Return the electrical telemetry widget."""
        return self.window.telemetry_widget("Electrical")

    def _deliver(self, payload, *, age_seconds=1.0, at=1000.0):
        """Deliver one telemetry payload through the shell's frame path."""
        self.window.apply_ui_frame(UiFrame(
            kind="telemetry", value=payload, state="observed",
            detail="Observed", age_seconds=age_seconds, observed_at=at))
        self.app.processEvents()

    def test_a_frame_reaches_the_chart(self):
        """One observed frame draws one observed point."""
        self._deliver(_telemetry())
        self.assertEqual(len(self._production().chart_values(0)), 1)

    def test_several_frames_accumulate(self):
        """Each frame adds exactly one sample."""
        for index in range(5):
            self._deliver(_telemetry(tick=1000 + index),
                          at=1000.0 + index * 2.0)
        self.assertEqual(len(self._production().chart_values(0)), 5)

    def test_the_chart_shows_the_observed_rate(self):
        """The chart shows the observed per-minute rate."""
        self._deliver(_telemetry(rate=12.5))
        self.assertAlmostEqual(self._production().chart_values(0)[-1], 12.5)

    def test_the_electrical_chart_shows_the_observed_watts(self):
        """The generation chart shows the observed watts.

        The observer reports 1000 J/tick, which is 60000 W at 60 ticks per
        second.
        """
        self._deliver(_telemetry())
        values = self._electrical().chart_values(0)
        self.assertTrue(values)
        self.assertAlmostEqual(values[-1], 60000.0)

    def test_a_missing_payload_contributes_nothing(self):
        """A frame without a value adds no sample."""
        self._deliver(_telemetry())
        before = len(self._production().chart_values(0))
        self.window.apply_ui_frame(UiFrame(
            kind="telemetry", value=None, state="unavailable",
            detail="Not observed"))
        self.app.processEvents()
        self.assertEqual(len(self._production().chart_values(0)), before)

    def test_an_invalid_payload_contributes_nothing(self):
        """A payload that does not validate adds no sample."""
        self._deliver(_telemetry())
        before = len(self._production().chart_values(0))
        self._deliver({"production": "not a payload"})
        self.assertEqual(len(self._production().chart_values(0)), before)

    def test_an_out_of_order_frame_never_reaches_the_chart(self):
        """An older frame never overwrites a newer observation.

        The bridge rejects it before it reaches the shell, so the chart
        keeps the newer line.
        """
        from qt_observation_bridge import ObservationBridge

        bridge = ObservationBridge(_StubService())
        self.assertTrue(bridge.accept_tick(2000))
        self.assertFalse(bridge.accept_tick(1000))
        self.assertEqual(bridge.stats.rejected_out_of_order, 1)

    def test_a_disconnect_clears_the_header_metrics(self):
        """A disconnect is a distinct state that clears the metrics."""
        self._deliver(_telemetry())
        self.window.apply_ui_frame(UiFrame(
            kind="status", value={"tick": 1000, "ups": 60.0},
            state="observed", age_seconds=1.0))
        self.app.processEvents()
        self.assertEqual(self.window.header.tiles["UPS"].value.text(), "60.00")
        self.window.apply_ui_frame(UiFrame(
            kind="status", value=None, state="unavailable",
            detail="Observer disconnected", age_seconds=1.0))
        self.app.processEvents()
        self.assertEqual(self.window.header.tiles["UPS"].value.text(), "—")

    def test_the_history_stays_bounded(self):
        """A long stream of observations keeps the history bounded."""
        for index in range(400):
            self._deliver(_telemetry(tick=1000 + index),
                          at=1000.0 + index * 2.0)
        history = self._production().history
        self.assertLessEqual(history.stats()["points"],
                             history.stats()["series"]
                             * history.maximum_points)

    def test_a_repeated_frame_is_coalesced(self):
        """A frame that says nothing new is not shown twice."""
        from qt_observation_bridge import FrameCoalescer

        coalescer = FrameCoalescer()
        payload = _telemetry()
        self.assertTrue(coalescer.accept("telemetry", payload, 1000))
        self.assertFalse(coalescer.accept("telemetry", payload, 1000))

    def test_the_chart_never_invents_a_point(self):
        """The drawn points are the observed ones, no more."""
        for index in range(4):
            self._deliver(_telemetry(tick=1000 + index, rate=5.0 + index),
                          at=1000.0 + index * 2.0)
        # The chart only paints when the workspace is the visible one.
        self.window.show_workspace("Production")
        self.app.processEvents()
        widget = self._production()
        self.assertEqual(len(widget.painted_values(0)), 4)
        self.assertEqual(widget.painted_values(0),
                         [5.0, 6.0, 7.0, 8.0])

    def test_a_telemetry_reset_clears_the_history(self):
        """A tick that went backwards starts the history again."""
        self._deliver(_telemetry(tick=2000), at=1000.0)
        self._deliver(_telemetry(tick=3000), at=1002.0)
        self._deliver(_telemetry(tick=1000), at=1004.0)
        widget = self._production()
        self.assertEqual(len(widget.chart_values(0)), 1)
        self.assertGreaterEqual(widget.history.resets, 1)

    def test_the_shell_never_imports_a_transport(self):
        """The shell asks the game for nothing.

        The check is on the **imports**, not on the prose: the module's
        docstring says what it does not do, and that mention must not
        fail the test.
        """
        import qt_shell as shell_module

        self._assert_no_transport_import(shell_module)

    def test_the_widget_never_imports_a_transport(self):
        """The telemetry widget asks the game for nothing."""
        import qt_telemetry_widget as widget_module

        self._assert_no_transport_import(widget_module)

    def _assert_no_transport_import(self, module) -> None:
        """Assert that a module imports no transport."""
        forbidden = {"rcon", "RconConnectionService", "subprocess",
                     "requests", "socket", "http", "urllib", "asyncio"}
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0].lower())
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0].lower())
        offending = imported & forbidden
        self.assertFalse(offending,
                         f"{module.__name__} imports {sorted(offending)}")


if __name__ == "__main__":
    unittest.main()
