"""World/screen map projection regression tests; no GUI required."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from dashboard_view import entity_screen_bounds, map_scale, project, unproject, viewport_radius


class MapProjectionTests(unittest.TestCase):
    def test_world_origin_at_view_center(self):
        center = {"x": 142.25, "y": -80.75}
        self.assertEqual(project(center, center, 800, 600, 60), (400, 300))

    def test_one_tile_world_spacing_is_exact_scale(self):
        center = {"x": 0, "y": 0}
        left = project({"x": -1, "y": 0}, center, 800, 600, 60)
        right = project({"x": 0, "y": 0}, center, 800, 600, 60)
        self.assertEqual(right[0] - left[0], 5)
        self.assertEqual(map_scale(800, 600, 60), 5)

    def test_roundtrip_for_negative_and_fractional_coordinates(self):
        center = {"x": -920.25, "y": 51.5}
        point = {"x": -915.875, "y": 62.125}
        x, y = project(point, center, 1017, 503, 24)
        recovered = unproject(x, y, center, 1017, 503, 24)
        self.assertAlmostEqual(recovered["x"], point["x"])
        self.assertAlmostEqual(recovered["y"], point["y"])

    def test_projection_is_not_clamped_to_128_tiles(self):
        center = {"x": 9000, "y": -9000}
        point = {"x": 9100, "y": -8900}
        p = unproject(*project(point, center, 800, 600, 200), center, 800, 600, 200)
        self.assertAlmostEqual(p["x"], point["x"])
        self.assertAlmostEqual(p["y"], point["y"])

    def test_local_default_radius_fits_256_tile_observation(self):
        self.assertLessEqual(2 * viewport_radius("60", 600, 400), 256)

    def test_one_to_one_pixel_tile_scale(self):
        radius = viewport_radius("1:1", 800, 600)
        self.assertEqual(map_scale(800, 600, radius), 1)
        self.assertEqual(viewport_radius("60", 800, 600), 60)

    def test_observed_entity_dimensions_use_world_scale(self):
        self.assertEqual(
            entity_screen_bounds({"width": 3, "height": 2}, 100, 100, 4),
            (94, 96, 106, 104),
        )

    def test_world_bounding_box_preserves_asymmetric_offsets(self):
        e = {"x": 11, "y": 7, "bounds": {
            "left_top": {"x": 9.5, "y": 6},
            "right_bottom": {"x": 12.5, "y": 8}}}
        self.assertEqual(entity_screen_bounds(e, 100, 100, 4), (94, 96, 106, 104))

    def test_resource_geometry_does_not_need_machine_footprint(self):
        self.assertEqual(entity_screen_bounds({"x": 1, "y": 2, "width": 1, "height": 1}, 5, 5, 2), (4, 4, 6, 6))

    def test_rocks_and_trees_remain_separate_nature_symbols(self):
        # R08 replaced the old generic circle with the prototype-driven nature
        # layer. Trees and rocks are still separate symbols, but they are now
        # separated by the observed prototype type and the observed chart
        # colour, not by guessing from the entity name.
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        source = (root / "agent" / "dashboard_view.py").read_text(encoding="utf-8")
        self.assertIn('if kind == "nature":', source)
        self.assertIn("def draw_nature", source)
        self.assertIn("def _draw_tree", source)
        self.assertIn("def _draw_rock", source)
        self.assertIn('tags="nature-tree"', source)
        self.assertIn('tags="nature-rock"', source)
        # The name-based guess is gone: classification uses observed data.
        self.assertNotIn('"rock" in name', source)

        nature = (root / "agent" / "dashboard_nature_layers.py").read_text(encoding="utf-8")
        self.assertIn('TREE_PROTOTYPE_TYPES = ("tree",)', nature)
        self.assertIn('ROCK_PROTOTYPE_TYPES = ("simple-entity",)', nature)
        self.assertIn('CLIFF_PROTOTYPE_TYPES = ("cliff",)', nature)

    def test_unknown_entity_dimensions_remain_unknown(self):
        self.assertIsNone(entity_screen_bounds({"name": "furnace"}, 100, 100, 4))

    def test_bad_dimensions_fail(self):
        for dims in ((0, 500, 60), (800, -1, 60), (800, 600, 0)):
            with self.subTest(dims=dims), self.assertRaises(ValueError):
                map_scale(*dims)


if __name__ == "__main__":
    unittest.main()
