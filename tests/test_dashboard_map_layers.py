"""Focused tests for the dashboard resource-patch map layer.

These cover the behaviour that replaces the per-deposit outlined shapes:
continuous patches, no invented tiles, exact observed geometry only.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_map_layers import (
    occupied_tiles,
    resource_patch_cells,
    resource_patch_color,
    resource_patch_rectangles,
)


def ore(x, y, name="iron-ore", **extra):
    entity = dict(x=x, y=y, name=name, kind="resource")
    entity.update(extra)
    return entity


class ResourcePatchColorTests(unittest.TestCase):
    def test_colors_match_the_verified_2_1_23_map_colors(self):
        # Values transcribed from data/base/prototypes/entity/resources.lua.
        self.assertEqual(resource_patch_color("iron-ore"), "#6a8694")
        self.assertEqual(resource_patch_color("copper-ore"), "#cd6337")
        self.assertEqual(resource_patch_color("stone"), "#b09c6d")
        self.assertEqual(resource_patch_color("uranium-ore"), "#00b300")

    def test_coal_keeps_the_game_hue_but_stays_legible(self):
        coal = resource_patch_color("coal")
        self.assertTrue(coal.startswith("#"))
        self.assertNotEqual(coal, "#000000")

    def test_unknown_resource_gets_a_stable_fallback(self):
        self.assertEqual(resource_patch_color("mystery-ore"), resource_patch_color("mystery-ore"))


class OccupiedTileTests(unittest.TestCase):
    def test_position_only_entity_occupies_exactly_one_tile(self):
        self.assertEqual(occupied_tiles(ore(3.5, -2.25)), [(3, -3)])

    def test_observed_bounds_expand_to_the_covered_tiles(self):
        entity = ore(
            0,
            0,
            bounds={
                "left_top": {"x": 0.0, "y": 0.0},
                "right_bottom": {"x": 2.0, "y": 2.0},
            },
        )
        self.assertEqual(
            occupied_tiles(entity), [(0, 0), (1, 0), (0, 1), (1, 1)]
        )

    def test_observed_width_and_height_expand_to_the_covered_tiles(self):
        entity = ore(0.0, 0.0, width=2.0, height=2.0)
        self.assertEqual(
            occupied_tiles(entity), [(-1, -1), (0, -1), (-1, 0), (0, 0)]
        )

    def test_no_geometry_is_inferred_from_the_name(self):
        # A named resource with no observed geometry must occupy one tile.
        self.assertEqual(len(occupied_tiles(ore(1.0, 1.0, "iron-ore"))), 1)

    def test_invalid_geometry_contributes_no_tiles(self):
        self.assertEqual(occupied_tiles(ore(1.0, 1.0, width=0, height=2)), [])
        self.assertEqual(occupied_tiles(ore(1.0, 1.0, width=float("nan"), height=2)), [])
        self.assertEqual(occupied_tiles(dict(x="a", y=1.0, name="iron-ore")), [])
        self.assertEqual(occupied_tiles(dict(x=1.0, y=1.0, bounds={})), [])

    def test_boolean_is_not_accepted_as_a_coordinate(self):
        entity = ore(
            0,
            0,
            bounds={
                "left_top": {"x": True, "y": 0.0},
                "right_bottom": {"x": 2.0, "y": 2.0},
            },
        )
        self.assertEqual(occupied_tiles(entity), [])

    def test_bounds_with_a_missing_corner_contribute_no_tiles(self):
        entity = ore(
            0,
            0,
            bounds={
                "left_top": {"x": 0.0, "y": 0.0},
                "right_bottom": {"y": 2.0},
            },
        )
        self.assertEqual(occupied_tiles(entity), [])


class ResourcePatchCellTests(unittest.TestCase):
    def test_adjacent_deposits_merge_into_one_continuous_patch(self):
        entities = [
            ore(0, 0, bounds=_box(0, 0, 1, 1)),
            ore(1, 0, bounds=_box(1, 0, 2, 1)),
            ore(2, 0, bounds=_box(2, 0, 3, 1)),
        ]
        patches = resource_patch_cells(entities)
        self.assertEqual(patches["iron-ore"], {(0, 0), (1, 0), (2, 0)})

    def test_different_resources_keep_separate_patches(self):
        entities = [ore(0, 0, "iron-ore"), ore(1, 1, "copper-ore")]
        patches = resource_patch_cells(entities)
        self.assertEqual(set(patches), {"iron-ore", "copper-ore"})

    def test_non_resource_entities_are_ignored(self):
        entities = [
            dict(x=0, y=0, name="iron-ore", kind="building"),
            dict(x=1, y=1, name="tree", kind="nature"),
        ]
        self.assertEqual(resource_patch_cells(entities), {})

    def test_origin_window_drops_tiles_outside_the_chart(self):
        origin = dict(x=0, y=0, width=4, height=4)
        entities = [ore(0, 0), ore(9, 9)]
        patches = resource_patch_cells(entities, origin)
        self.assertEqual(patches["iron-ore"], {(0, 0)})

    def test_no_observed_resource_means_no_patch(self):
        self.assertEqual(resource_patch_cells([]), {})
        self.assertEqual(resource_patch_cells([dict(x=0, y=0, name="iron-ore")]), {})


class ResourcePatchRectangleTests(unittest.TestCase):
    def test_dense_field_closes_supported_one_tile_pinhole(self):
        deposits = [ore(x, y) for x, y in ((0, 1), (1, 0), (2, 1), (1, 2))]
        rectangles = resource_patch_rectangles(deposits)["iron-ore"]
        displayed = {(x, y) for x0, y0, x1, y1 in rectangles
                     for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
        self.assertIn((1, 1), displayed)
        self.assertNotIn((3, 1), displayed)
        self.assertEqual(len(resource_patch_cells(deposits)["iron-ore"]), 4)

    def test_one_tile_gap_between_sparse_deposits_remains_empty(self):
        rectangles = resource_patch_rectangles([ore(0, 0), ore(2, 0)])["iron-ore"]
        self.assertEqual(len(rectangles), 2)

    def test_a_row_of_deposits_becomes_one_filled_rectangle(self):
        entities = [
            ore(0, 0, bounds=_box(0, 0, 1, 1)),
            ore(1, 0, bounds=_box(1, 0, 2, 1)),
        ]
        rects = resource_patch_rectangles(entities)["iron-ore"]
        self.assertEqual(rects, [(0, 0, 1, 0)])

    def test_a_block_becomes_one_rectangle(self):
        entities = [ore(0, 0, bounds=_box(0, 0, 2, 2))]
        rects = resource_patch_rectangles(entities)["iron-ore"]
        self.assertEqual(rects, [(0, 0, 1, 1)])

    def test_separated_patches_stay_separate(self):
        entities = [ore(0, 0), ore(10, 10)]
        rects = resource_patch_rectangles(entities)["iron-ore"]
        self.assertEqual(len(rects), 2)

    def test_rectangles_never_span_more_tiles_than_were_observed(self):
        entities = [ore(0, 0), ore(1, 0), ore(0, 1)]
        rects = resource_patch_rectangles(entities)["iron-ore"]
        covered = set()
        for x0, y0, x1, y1 in rects:
            for tx in range(x0, x1 + 1):
                for ty in range(y0, y1 + 1):
                    covered.add((tx, ty))
        self.assertEqual(covered, {(0, 0), (1, 0), (0, 1)})


def _box(x0, y0, x1, y1):
    return {
        "left_top": {"x": float(x0), "y": float(y0)},
        "right_bottom": {"x": float(x1), "y": float(y1)},
    }


if __name__ == "__main__":
    unittest.main()
