"""Seeded property tests for the dashboard resource-patch layer.

The critical truthfulness property is that a merged patch covers exactly
the tiles the observer reported: no invented tile and no dropped tile.
The sweep is seeded so a failure is reproducible.
"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_map_layers import merged_patch_rectangles, resource_patch_cells

SEED = 20261024


def covered_tiles(rectangles):
    covered = set()
    for x0, y0, x1, y1 in rectangles:
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                covered.add((tx, ty))
    return covered


class PatchRectanglePropertyTests(unittest.TestCase):
    def test_merged_rectangles_cover_exactly_the_observed_tiles(self):
        random.seed(SEED)
        for trial in range(300):
            tiles = {
                (random.randint(-20, 20), random.randint(-20, 20))
                for _ in range(random.randint(1, 30))
            }
            with self.subTest(trial=trial):
                self.assertEqual(
                    covered_tiles(merged_patch_rectangles(tiles)), tiles
                )

    def test_patch_cells_cover_exactly_the_observed_tiles(self):
        random.seed(SEED)
        for trial in range(200):
            entities = []
            expected = set()
            for _ in range(random.randint(1, 20)):
                x = random.randint(-30, 30)
                y = random.randint(-30, 30)
                entities.append(dict(x=x, y=y, name="iron-ore", kind="resource"))
                expected.add((x, y))
            with self.subTest(trial=trial):
                patches = resource_patch_cells(entities)
                self.assertEqual(patches.get("iron-ore", set()), expected)

    def test_patch_rectangles_never_exceed_the_observed_tiles(self):
        random.seed(SEED)
        for trial in range(200):
            entities = []
            expected = set()
            for _ in range(random.randint(1, 20)):
                x = random.randint(-30, 30)
                y = random.randint(-30, 30)
                entities.append(
                    dict(
                        x=x,
                        y=y,
                        name="copper-ore",
                        kind="resource",
                        bounds={
                            "left_top": {"x": float(x), "y": float(y)},
                            "right_bottom": {"x": float(x) + 1, "y": float(y) + 1},
                        },
                    )
                )
                expected.add((x, y))
            with self.subTest(trial=trial):
                rects = resource_patch_cells(entities).get("copper-ore", set())
                self.assertEqual(
                    covered_tiles(merged_patch_rectangles(rects)), expected
                )


if __name__ == "__main__":
    unittest.main()
