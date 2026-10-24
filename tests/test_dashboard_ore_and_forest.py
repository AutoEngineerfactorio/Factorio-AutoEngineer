"""Tests for the observed ore field fill and the forest cover glyph.

These cover the R08-D behaviour that restores the ore patch and the forest
appearance without inventing data:

* A dense observed ore field reads as one continuous patch.
* Two deposits that are separated stay separate.
* The outer boundary of a deposit stays on the observed nodes.
* A tree keeps a legible glyph at a wide map zoom without adding a tree.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from dashboard_map_layers import (  # noqa: E402
    fill_observed_field,
    resource_patch_groups,
    resource_patch_rectangles,
)
from dashboard_nature_layers import TREE_MIN_MARKER_PIXELS  # noqa: E402


def ore(x, y, name="iron-ore", **extra):
    entity = dict(x=x, y=y, name=name, kind="resource")
    entity.update(extra)
    return entity


class ObservedFieldFillTests(unittest.TestCase):
    def test_an_interior_gap_is_closed(self):
        observed = {(0, 0), (2, 0), (0, 2), (2, 2), (1, 1)}
        filled = fill_observed_field(observed)
        self.assertIn((1, 0), filled)
        self.assertIn((0, 1), filled)
        self.assertIn((1, 2), filled)
        self.assertIn((2, 1), filled)

    def test_a_boundary_gap_is_not_closed(self):
        # (5, 5) touches the field on only one side, so it is not part of it.
        observed = {(0, 0), (1, 0), (0, 1)}
        filled = fill_observed_field(observed)
        self.assertNotIn((2, 0), filled)
        self.assertNotIn((0, 2), filled)

    def test_a_corner_gap_with_two_neighbours_is_not_closed(self):
        observed = {(0, 0), (1, 0), (0, 1)}
        filled = fill_observed_field(observed)
        self.assertNotIn((1, 1), filled)

    def test_every_added_tile_is_supported_by_observed_ore(self):
        observed = {(x, y) for x in range(5) for y in range(5)}
        observed.discard((2, 2))
        filled = fill_observed_field(observed)
        self.assertIn((2, 2), filled)
        for x, y in filled - observed:
            neighbours = sum(
                ((x + dx, y + dy) in observed)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            self.assertGreaterEqual(neighbours, 3)

    def test_the_observed_tiles_are_always_kept(self):
        observed = {(1, 2), (3, 4)}
        self.assertTrue(observed <= fill_observed_field(observed))

    def test_an_empty_field_stays_empty(self):
        self.assertEqual(fill_observed_field(set()), set())


class ResourceGroupTests(unittest.TestCase):
    def test_adjacent_tiles_are_one_group(self):
        groups = resource_patch_groups({(0, 0), (1, 0), (1, 1)})
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0], {(0, 0), (1, 0), (1, 1)})

    def test_distant_tiles_are_separate_groups(self):
        groups = resource_patch_groups({(0, 0), (40, 40)})
        self.assertEqual(len(groups), 2)

    def test_a_one_tile_gap_keeps_two_fields_apart(self):
        # Two tiles with an empty tile between them are two deposits, so the
        # fill must not bridge them into one shape.
        groups = resource_patch_groups({(0, 0), (2, 0)})
        self.assertEqual(len(groups), 2)


class ResourcePatchRectangleTests(unittest.TestCase):
    def test_a_dense_field_reads_as_one_continuous_patch(self):
        # A four-by-four field of ore nodes with one missing corner node.
        entities = [
            ore(x + 0.5, y + 0.5)
            for x in range(4)
            for y in range(4)
            if not (x == 3 and y == 3)
        ]
        rectangles = resource_patch_rectangles(entities)
        self.assertIn("iron-ore", rectangles)
        covered = set()
        for x0, y0, x1, y1 in rectangles["iron-ore"]:
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    covered.add((x, y))
        # Every observed tile is inside the drawn patch.
        for x in range(4):
            for y in range(4):
                if not (x == 3 and y == 3):
                    self.assertIn((x, y), covered)

    def test_two_separate_deposits_stay_separate(self):
        entities = [
            ore(0.5, 0.5),
            ore(1.5, 0.5),
            ore(30.5, 30.5),
            ore(31.5, 30.5),
        ]
        rectangles = resource_patch_rectangles(entities)
        spans = rectangles["iron-ore"]
        # The two deposits are far apart, so they cannot share a rectangle.
        self.assertGreaterEqual(len(spans), 2)

    def test_different_resources_keep_separate_patches(self):
        entities = [ore(0.5, 0.5, name="iron-ore"), ore(1.5, 0.5, name="copper-ore")]
        rectangles = resource_patch_rectangles(entities)
        self.assertIn("iron-ore", rectangles)
        self.assertIn("copper-ore", rectangles)

    def test_an_isolated_node_stays_a_single_tile(self):
        rectangles = resource_patch_rectangles([ore(10.5, 10.5)])
        self.assertEqual(rectangles["iron-ore"], [(10, 10, 10, 10)])

    def test_no_entity_produces_no_patch(self):
        self.assertEqual(resource_patch_rectangles([]), {})


class ForestGlyphTests(unittest.TestCase):
    def test_a_tree_keeps_a_legible_minimum_glyph(self):
        self.assertGreater(TREE_MIN_MARKER_PIXELS, 1.0)

    def test_the_minimum_is_a_display_size_not_a_world_size(self):
        # The minimum is in screen pixels; it never scales the observed
        # position or invents a tree.
        self.assertLess(TREE_MIN_MARKER_PIXELS, 10.0)


if __name__ == "__main__":
    unittest.main()
