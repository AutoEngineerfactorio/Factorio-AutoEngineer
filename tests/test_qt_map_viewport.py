"""Regression tests for the Qt map viewport geometry.

These tests import no Qt module: the viewport is pure geometry, and it
must stay verifiable without a display server.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import qt_map_viewport as viewport_module  # noqa: E402
from dashboard_chunk_grid import CHUNK_TILES  # noqa: E402


class ViewportConstructionTests(unittest.TestCase):
    """The viewport keeps its values inside the accepted range."""

    def test_a_default_viewport_is_valid(self):
        viewport = viewport_module.Viewport()
        self.assertEqual(viewport.radius, 128.0)

    def test_the_radius_is_clamped(self):
        self.assertEqual(
            viewport_module.Viewport(radius=0.1).radius,
            viewport_module.MIN_RADIUS,
        )
        self.assertEqual(
            viewport_module.Viewport(radius=1e9).radius,
            viewport_module.MAX_RADIUS,
        )

    def test_a_non_finite_radius_is_rejected(self):
        with self.assertRaises(ValueError):
            viewport_module.Viewport(radius=float("nan"))
        with self.assertRaises(ValueError):
            viewport_module.Viewport(radius=float("inf"))

    def test_a_non_finite_center_is_rejected(self):
        with self.assertRaises(ValueError):
            viewport_module.Viewport(center_x=float("nan"))
        with self.assertRaises(ValueError):
            viewport_module.Viewport(center_y=float("inf"))

    def test_the_viewport_is_immutable(self):
        viewport = viewport_module.Viewport()
        with self.assertRaises(Exception):
            viewport.center_x = 5.0  # type: ignore[misc]


class ProjectionTests(unittest.TestCase):
    """The projection matches the Tkinter dashboard's own projection."""

    def test_the_center_projects_to_the_middle_of_the_viewport(self):
        viewport = viewport_module.Viewport(center_x=100.0, center_y=50.0)
        x, y = viewport.project(100.0, 50.0, 800, 600)
        self.assertAlmostEqual(x, 400.0)
        self.assertAlmostEqual(y, 300.0)

    def test_projection_and_unprojection_are_inverses(self):
        viewport = viewport_module.Viewport(center_x=12.5, center_y=-8.0,
                                           radius=64.0)
        for world_x, world_y in ((0.0, 0.0), (100.0, 50.0), (-30.0, 70.0)):
            screen_x, screen_y = viewport.project(world_x, world_y, 1024, 768)
            back_x, back_y = viewport.unproject(screen_x, screen_y, 1024, 768)
            self.assertAlmostEqual(back_x, world_x, places=6)
            self.assertAlmostEqual(back_y, world_y, places=6)

    def test_the_projection_matches_the_tkinter_dashboard(self):
        """Both dashboards must show the factory in the same place."""
        from dashboard_view import project as tk_project

        viewport = viewport_module.Viewport(center_x=30.0, center_y=-12.0,
                                           radius=96.0)
        width, height = 1200, 800
        scale = min(width, height) / (2 * 96.0)
        for world_x, world_y in ((0.0, 0.0), (55.5, 22.25), (-40.0, 60.0)):
            expected = tk_project(
                {"x": world_x, "y": world_y},
                {"x": 30.0, "y": -12.0},
                width, height, 96.0,
            )
            actual = viewport.project(world_x, world_y, width, height)
            self.assertAlmostEqual(actual[0], expected[0], places=9)
            self.assertAlmostEqual(actual[1], expected[1], places=9)
            self.assertEqual(scale, viewport.pixels_per_tile(width, height))

    def test_an_invalid_viewport_size_is_rejected(self):
        viewport = viewport_module.Viewport()
        with self.assertRaises(ValueError):
            viewport.project(0.0, 0.0, 0, 600)
        with self.assertRaises(ValueError):
            viewport.pixels_per_tile(800, 0)

    def test_contains_reports_the_visible_area(self):
        viewport = viewport_module.Viewport()
        self.assertTrue(viewport.contains(0.0, 0.0, 800, 600))
        self.assertFalse(viewport.contains(100000.0, 0.0, 800, 600))


class MovementTests(unittest.TestCase):
    """Panning and zooming behave the way a map user expects."""

    def test_panning_right_moves_the_view_left(self):
        viewport = viewport_module.Viewport(center_x=0.0, center_y=0.0)
        panned = viewport.panned(10.0, 0.0, 800, 600)
        self.assertLess(panned.center_x, viewport.center_x)

    def test_panning_by_zero_keeps_the_center(self):
        viewport = viewport_module.Viewport(center_x=7.0, center_y=9.0)
        panned = viewport.panned(0.0, 0.0, 800, 600)
        self.assertEqual(panned.center_x, 7.0)
        self.assertEqual(panned.center_y, 9.0)

    def test_an_oversized_pan_is_rejected(self):
        viewport = viewport_module.Viewport()
        with self.assertRaises(ValueError):
            viewport.panned(999999.0, 0.0, 800, 600)

    def test_a_non_finite_pan_is_rejected(self):
        viewport = viewport_module.Viewport()
        with self.assertRaises(ValueError):
            viewport.panned(float("nan"), 0.0, 800, 600)

    def test_zooming_in_reduces_the_radius(self):
        viewport = viewport_module.Viewport(radius=128.0)
        zoomed = viewport.zoomed(2.0, 800, 600)
        self.assertAlmostEqual(zoomed.radius, 64.0)

    def test_zooming_out_increases_the_radius(self):
        viewport = viewport_module.Viewport(radius=128.0)
        zoomed = viewport.zoomed(0.5, 800, 600)
        self.assertAlmostEqual(zoomed.radius, 256.0)

    def test_zooming_keeps_the_focus_point_under_the_cursor(self):
        viewport = viewport_module.Viewport(center_x=0.0, center_y=0.0,
                                           radius=128.0)
        focus_x, focus_y = 250.0, 400.0
        zoomed = viewport.zoomed(2.0, 800, 600, focus_x, focus_y)
        before = viewport.unproject(focus_x, focus_y, 800, 600)
        after = zoomed.unproject(focus_x, focus_y, 800, 600)
        self.assertAlmostEqual(before[0], after[0], places=6)
        self.assertAlmostEqual(before[1], after[1], places=6)

    def test_zooming_without_a_focus_keeps_the_center(self):
        viewport = viewport_module.Viewport(center_x=15.0, center_y=-3.0)
        zoomed = viewport.zoomed(2.0, 800, 600)
        self.assertEqual(zoomed.center_x, 15.0)
        self.assertEqual(zoomed.center_y, -3.0)

    def test_an_invalid_zoom_factor_is_rejected(self):
        viewport = viewport_module.Viewport()
        with self.assertRaises(ValueError):
            viewport.zoomed(0.0, 800, 600)
        with self.assertRaises(ValueError):
            viewport.zoomed(-1.0, 800, 600)
        with self.assertRaises(ValueError):
            viewport.zoomed(float("nan"), 800, 600)

    def test_zooming_beyond_the_limit_is_clamped(self):
        viewport = viewport_module.Viewport(radius=viewport_module.MIN_RADIUS)
        zoomed = viewport.zoomed(1000.0, 800, 600)
        self.assertGreaterEqual(zoomed.radius, viewport_module.MIN_RADIUS)

    def test_centering_on_a_position(self):
        viewport = viewport_module.Viewport()
        centred = viewport.centred_on(50.0, -20.0)
        self.assertEqual(centred.center_x, 50.0)
        self.assertEqual(centred.center_y, -20.0)

    def test_centering_on_an_invalid_position_is_rejected(self):
        viewport = viewport_module.Viewport()
        with self.assertRaises(ValueError):
            viewport.centred_on(float("nan"), 0.0)


class ChunkSelectionTests(unittest.TestCase):
    """The viewport asks for bounded, nearest-first chunk sets."""

    def test_the_visible_chunks_are_on_the_aligned_grid(self):
        viewport = viewport_module.Viewport(center_x=0.0, center_y=0.0,
                                           radius=128.0)
        for chunk_x, chunk_y in viewport.visible_chunks(800, 600):
            self.assertIsInstance(chunk_x, int)
            self.assertIsInstance(chunk_y, int)

    def test_the_chunk_set_is_bounded(self):
        viewport = viewport_module.Viewport(radius=4096.0)
        chunks = viewport.visible_chunks(3840, 2160, limit=16)
        self.assertLessEqual(len(chunks), 16)

    def test_the_nearest_chunk_is_first(self):
        viewport = viewport_module.Viewport(center_x=0.0, center_y=0.0,
                                           radius=64.0)
        chunks = viewport.visible_chunks(800, 600)
        self.assertEqual(chunks[0], (0, 0))

    def test_the_chunk_set_follows_the_center(self):
        """The nearest chunk is the one the centre sits inside.

        The centre is placed well inside the chunk so the test does not
        sit on a chunk boundary, where two chunks are equally near.
        """
        viewport = viewport_module.Viewport(
            center_x=CHUNK_TILES * 10 + 32, center_y=0.0, radius=64.0)
        chunks = viewport.visible_chunks(800, 600)
        self.assertEqual(chunks[0][0], 10)

    def test_a_centre_on_a_chunk_boundary_belongs_to_the_upper_chunk(self):
        """The chunk that contains the centre tile ranks first.

        Tile 640 is the first tile of chunk 10, so chunk 10 is the
        chunk the user is standing in.
        """
        viewport = viewport_module.Viewport(
            center_x=CHUNK_TILES * 10, center_y=0.0, radius=64.0)
        chunks = viewport.visible_chunks(800, 600)
        self.assertEqual(chunks[0][0], 10)
        self.assertIn((9, 0), chunks)

    def test_a_limit_below_one_still_returns_one_chunk(self):
        viewport = viewport_module.Viewport()
        self.assertEqual(len(viewport.visible_chunks(800, 600, limit=0)), 1)


class CacheKeyTests(unittest.TestCase):
    """The cache key decides whether a redraw is needed at all."""

    def test_the_same_viewport_has_the_same_key(self):
        viewport = viewport_module.Viewport(center_x=1.0, center_y=2.0)
        other = viewport_module.Viewport(center_x=1.0, center_y=2.0)
        self.assertEqual(
            viewport.cache_key(800, 600), other.cache_key(800, 600))

    def test_a_different_center_has_a_different_key(self):
        first = viewport_module.Viewport(center_x=1.0)
        second = viewport_module.Viewport(center_x=2.0)
        self.assertNotEqual(
            first.cache_key(800, 600), second.cache_key(800, 600))

    def test_a_different_size_has_a_different_key(self):
        viewport = viewport_module.Viewport()
        self.assertNotEqual(
            viewport.cache_key(800, 600), viewport.cache_key(1024, 768))

    def test_a_different_content_key_has_a_different_key(self):
        viewport = viewport_module.Viewport()
        self.assertNotEqual(
            viewport.cache_key(800, 600, "a"), viewport.cache_key(800, 600, "b"))

    def test_the_same_content_key_has_the_same_key(self):
        viewport = viewport_module.Viewport()
        self.assertEqual(
            viewport.cache_key(800, 600, "a"), viewport.cache_key(800, 600, "a"))

    def test_a_tiny_center_move_changes_the_key(self):
        """A redraw must happen when the map moves at all."""
        first = viewport_module.Viewport(center_x=0.0)
        second = viewport_module.Viewport(center_x=0.0001)
        self.assertNotEqual(
            first.cache_key(800, 600), second.cache_key(800, 600))


class FrameViewportTests(unittest.TestCase):
    """The viewport follows the observed player position."""

    def test_the_viewport_follows_the_player(self):
        frame = {"position": {"x": 100.0, "y": 50.0}}
        viewport = viewport_module.viewport_from_frame(frame)
        self.assertEqual(viewport.center_x, 100.0)
        self.assertEqual(viewport.center_y, 50.0)

    def test_a_frame_without_a_position_stays_at_the_origin(self):
        viewport = viewport_module.viewport_from_frame({"schema": 1})
        self.assertEqual(viewport.center_x, 0.0)
        self.assertEqual(viewport.center_y, 0.0)

    def test_a_malformed_position_is_ignored(self):
        frame = {"position": {"x": "nonsense", "y": None}}
        viewport = viewport_module.viewport_from_frame(frame)
        self.assertEqual(viewport.center_x, 0.0)
        self.assertEqual(viewport.center_y, 0.0)

    def test_a_none_frame_is_accepted(self):
        viewport = viewport_module.viewport_from_frame(None)
        self.assertEqual(viewport.center_x, 0.0)


class ZoomLabelTests(unittest.TestCase):
    """The zoom label names the level the user is at."""

    def test_an_offered_level_has_a_label(self):
        label = viewport_module.zoom_level_label(128.0)
        self.assertIn("128", label)

    def test_the_nearest_level_is_found(self):
        self.assertEqual(
            viewport_module.nearest_zoom_level(130.0), 128.0)
        self.assertEqual(
            viewport_module.nearest_zoom_level(60.0), 64.0)

    def test_the_label_is_never_empty(self):
        label = viewport_module.zoom_level_label(100.0)
        self.assertTrue(label)
        self.assertFalse(math.isnan(float(label.split()[0])))


class SurfaceScopeTests(unittest.TestCase):
    """Chunks from one surface are never drawn on another."""

    def test_the_default_surface_is_nauvis(self):
        self.assertEqual(
            viewport_module.Viewport().surface, "nauvis")

    def test_an_invalid_surface_is_rejected(self):
        with self.assertRaises(ValueError):
            viewport_module.Viewport(surface="")
        with self.assertRaises(ValueError):
            viewport_module.Viewport(surface="x" * 200)

    def test_switching_surface_resets_the_position(self):
        viewport = viewport_module.Viewport(center_x=500.0, center_y=300.0)
        switched = viewport.on_surface("vulcanus")
        self.assertEqual(switched.surface, "vulcanus")
        self.assertEqual(switched.center_x, 0.0)
        self.assertEqual(switched.center_y, 0.0)

    def test_switching_surface_keeps_the_zoom(self):
        viewport = viewport_module.Viewport(radius=256.0)
        switched = viewport.on_surface("vulcanus")
        self.assertEqual(switched.radius, 256.0)

    def test_switching_to_the_same_surface_changes_nothing(self):
        viewport = viewport_module.Viewport(center_x=500.0, center_y=300.0)
        self.assertIs(viewport.on_surface("nauvis"), viewport)

    def test_a_different_surface_has_a_different_cache_key(self):
        first = viewport_module.Viewport(surface="nauvis")
        second = viewport_module.Viewport(surface="vulcanus")
        self.assertNotEqual(
            first.cache_key(800, 600), second.cache_key(800, 600))

    def test_the_frame_surface_is_used(self):
        frame = {"position": {"x": 10.0, "y": 20.0}, "surface": "vulcanus"}
        viewport = viewport_module.viewport_from_frame(frame)
        self.assertEqual(viewport.surface, "vulcanus")
        self.assertEqual(viewport.center_x, 10.0)

    def test_a_frame_without_a_surface_keeps_the_default(self):
        viewport = viewport_module.viewport_from_frame({"schema": 1})
        self.assertEqual(viewport.surface, "nauvis")

    def test_a_malformed_surface_is_ignored(self):
        frame = {"surface": 12345}
        viewport = viewport_module.viewport_from_frame(frame)
        self.assertEqual(viewport.surface, "nauvis")


class ModulePurityTests(unittest.TestCase):
    """The viewport must stay testable without a display server."""

    def test_the_viewport_module_does_not_import_qt(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_map_viewport.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("PySide6", source)
        self.assertNotIn("QtWidgets", source)


if __name__ == "__main__":
    unittest.main()
