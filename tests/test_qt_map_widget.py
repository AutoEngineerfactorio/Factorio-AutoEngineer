"""Regression tests for the Qt map widget.

These tests need PySide6. They run on the **offscreen** platform plugin so
they need no display server, and they skip cleanly when PySide6 is not
installed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication
    QPoint = import_module("PySide6.QtCore").QPoint
    QWheelEvent = import_module("PySide6.QtGui").QWheelEvent
    QMouseEvent = import_module("PySide6.QtGui").QMouseEvent
    QEvent = import_module("PySide6.QtCore").QEvent

    import qt_map_viewport
    import qt_map_widget

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


def _frame():
    """Return a small observed map with one entity of each kind."""
    return {
        "origins": [(0, 0)],
        "entities": [
            {"kind": "building", "x": 10, "y": 10, "name": "assembler-1",
             "width": 3.0, "height": 3.0},
            {"kind": "enemy", "x": 20, "y": 20, "name": "small-biter"},
            {"kind": "nature", "x": 30, "y": 30, "name": "tree-01",
             "entity_type": "tree", "map_color": [0.61, 1.0, 0.88]},
            {"kind": "resource", "x": 40, "y": 40, "name": "iron-ore",
             "bounds": {"left_top": {"x": 39.5, "y": 39.5},
                        "right_bottom": {"x": 41.5, "y": 41.5}}},
        ],
        "terrain": {"tiles": [{"x": 0, "y": 0, "color": "#334455"}]},
        "overlays": {"available": {"pollution": True},
                     "pollution": [{"x": 50, "y": 50, "value": 10,
                                    "width": 4, "height": 4}]},
        "partial": False,
    }


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class MapWidgetTests(unittest.TestCase):
    """The map paints, pans, zooms and skips the repaints it does not need."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_map_widget.MapWidget(
            qt_map_viewport.Viewport(center_x=20.0, center_y=20.0,
                                     radius=64.0))
        self.widget.resize(800, 600)

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def _paint(self):
        """Force a paint and return the widget."""
        self.widget.show()
        self.app.processEvents()
        self.widget.repaint()
        self.app.processEvents()
        return self.widget

    def test_the_widget_builds_without_an_observation(self):
        self.assertIsNone(self.widget.scene)
        self._paint()

    def test_an_observation_builds_a_scene(self):
        self.widget.set_map(_frame(), player={"x": 5, "y": 5})
        scene = self.widget.scene
        self.assertIsNotNone(scene)
        assert scene is not None
        self.assertTrue(scene.primitives)

    def test_the_player_becomes_a_primitive(self):
        self.widget.set_map(_frame(), player={"x": 5, "y": 5})
        scene = self.widget.scene
        assert scene is not None
        self.assertEqual(len(scene.by_layer("player")), 1)

    def test_the_map_paints_without_an_observation(self):
        self._paint()
        self.assertGreaterEqual(self.widget.stats()["painted"], 1)

    def test_the_map_paints_with_an_observation(self):
        self.widget.set_map(_frame())
        self._paint()
        self.assertGreaterEqual(self.widget.stats()["painted"], 1)

    def test_an_unchanged_map_skips_the_repaint(self):
        """A tick that brings nothing new must not request a repaint.

        The skip lives in ``refresh()``, which is where the widget decides
        whether to ask Qt for a repaint at all. The paint event itself
        always paints, because a paint event for a fresh target - a
        render into an image, or a region exposed by another window -
        must not be skipped.
        """
        self.widget.set_map(_frame())
        self._paint()
        painted = self.widget.stats()["painted"]
        self.assertFalse(self.widget.refresh())
        self.assertFalse(self.widget.refresh())
        self.assertEqual(self.widget.stats()["painted"], painted)
        self.assertGreaterEqual(self.widget.stats()["skipped"], 2)

    def test_a_changed_map_requests_a_repaint(self):
        """A new observation must ask Qt for a repaint."""
        self.widget.set_map(_frame())
        self._paint()
        changed = _frame()
        changed["entities"][0]["x"] = 999
        self.widget.set_map(changed)
        self.assertTrue(self.widget.refresh())

    def test_the_paint_event_always_paints(self):
        """A paint event must draw, even when nothing changed.

        A render into a fresh image asks the widget to paint without
        changing anything. Skipping that would leave the image empty.
        """
        self.widget.set_map(_frame())
        self._paint()
        painted = self.widget.stats()["painted"]
        self.widget.repaint()
        self.app.processEvents()
        self.assertGreater(self.widget.stats()["painted"], painted)

    def test_a_new_observation_repaints(self):
        self.widget.set_map(_frame())
        self._paint()
        painted = self.widget.stats()["painted"]
        self.widget.set_map(_frame())
        self._paint()
        self.assertGreater(self.widget.stats()["painted"], painted)

    def test_a_layer_can_be_switched_off(self):
        self.widget.set_map(_frame())
        self.assertTrue(self.widget.layer_enabled("nature"))
        self.widget.set_layer("nature", False)
        self.assertFalse(self.widget.layer_enabled("nature"))

    def test_an_unknown_layer_is_rejected(self):
        with self.assertRaises(KeyError):
            self.widget.set_layer("no-such-layer", True)

    def test_toggling_a_layer_returns_its_new_state(self):
        self.assertFalse(self.widget.toggle_layer("enemy"))
        self.assertTrue(self.widget.toggle_layer("enemy"))

    def test_the_toggleable_layers_are_offered(self):
        self.assertIn("resource", self.widget.toggleable_layers)
        self.assertIn("enemy", self.widget.toggleable_layers)

    def test_a_viewport_change_is_announced(self):
        seen = []
        self.widget.viewportChanged.connect(seen.append)
        self.widget.set_viewport(
            qt_map_viewport.Viewport(center_x=1.0, center_y=2.0))
        self.assertEqual(len(seen), 1)

    def test_zooming_to_a_level_moves_the_view(self):
        self.widget.zoom_to_level(256.0)
        self.assertAlmostEqual(self.widget.viewport.radius, 256.0)

    def test_the_zoom_label_names_the_level(self):
        self.widget.zoom_to_level(128.0)
        self.assertIn("128", self.widget.zoom_label)

    def test_the_stats_report_the_primitive_count(self):
        self.widget.set_map(_frame())
        self.assertGreater(self.widget.stats()["primitives"], 0)

    def test_the_stats_report_the_surface(self):
        self.assertEqual(self.widget.stats()["surface"], "nauvis")

    def test_the_visible_chunks_are_bounded(self):
        """The map must never ask for an unbounded number of chunks."""
        chunks = self.widget.visible_chunks(limit=8)
        self.assertLessEqual(len(chunks), 8)

    def test_the_visible_chunks_follow_the_viewport(self):
        self.widget.set_viewport(qt_map_viewport.Viewport(
            center_x=640.0, center_y=0.0, radius=64.0))
        chunks = self.widget.visible_chunks()
        self.assertTrue(chunks)
        self.assertEqual(chunks[0][0], 10)

    def test_a_partial_map_is_reported_as_partial(self):
        frame = _frame()
        frame["partial"] = True
        self.widget.set_map(frame)
        self.assertTrue(self.widget.stats()["partial"])

    def test_observed_raster_is_painted_and_bad_indexes_are_rejected(self):
        raster = {"origin": {"x": 0, "y": 0}, "rows": ["00" * 64] * 64,
                  "palette": ["#123456"]}
        self.widget.set_map({"rasters": [raster]})
        self.assertEqual(self.widget.stats()["raster_chunks"], 1)
        self.widget.resize(400, 400)
        self.widget.show()
        self.app.processEvents()
        pixels = self.widget.grab().toImage()
        self.assertEqual(pixels.pixelColor(200, 200).name(), "#123456")
        bad = dict(raster, rows=["ff" * 64] * 64)
        self.widget.set_map({"rasters": [bad]})
        self.assertEqual(self.widget.stats()["raster_chunks"], 0)
        whitespace = dict(raster, rows=["00 " * 42 + "00"] * 64)
        self.widget.set_map({"rasters": [whitespace]})
        self.assertEqual(self.widget.stats()["raster_chunks"], 0)
        self.widget.set_map(None)
        self.assertEqual(self.widget.stats()["raster_chunks"], 0)

    def test_the_widget_holds_no_transport(self):
        """The map widget must not be able to command the game."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_map_widget.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("rcon", "call_tool", "send_command", "place_entity"):
            self.assertNotIn(forbidden, source.lower())

    def test_the_widget_survives_a_resize(self):
        self.widget.set_map(_frame())
        for width, height in ((480, 320), (2560, 1440), (1440, 900)):
            self.widget.resize(width, height)
            self.app.processEvents()
            self._paint()

    def test_the_widget_closes_cleanly(self):
        self.widget.set_map(_frame())
        self._paint()
        self.widget.close()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
