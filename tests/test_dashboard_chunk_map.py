"""Offline tests for assembling cached map chunks into one dashboard map."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

from dashboard_chunk_cache import ChunkCache  # noqa: E402
from dashboard_chunk_grid import CHUNK_TILES, chunk_origin  # noqa: E402
from dashboard_chunk_map import (  # noqa: E402
    entity_identity,
    merge_chunks,
    require,
    require_all,
)


def frame(chunk_x=0, chunk_y=0, entities=(), partial=False, chunk_complete=True, tiles=()):
    """Build one observed terrain frame for an aligned chunk."""
    origin = chunk_origin(chunk_x, chunk_y)
    return {
        "origin": {"x": origin["x"], "y": origin["y"]},
        "step": 1,
        "partial": partial,
        "chunk_complete": chunk_complete,
        "map_chunk": {"x": chunk_x, "y": chunk_y, "size": CHUNK_TILES},
        "entities": list(entities),
        "tiles": list(tiles),
    }


def nature(x, y, name="tree-01"):
    return {"x": x, "y": y, "name": name, "kind": "nature"}


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.cache = ChunkCache(max_chunks=8, max_age_seconds=60.0)
        self.cache.set_surface("nauvis")

    def test_merge_deduplicates_entities_at_a_shared_boundary(self):
        shared = nature(64.0, 10.0)
        self.cache.store(frame(0, 0, [nature(10.0, 10.0), shared]), tick=1)
        self.cache.store(frame(1, 0, [shared, nature(70.0, 10.0)]), tick=1)
        merged = merge_chunks(
            self.cache, require_all([self.cache.get(0, 0), self.cache.get(1, 0)]), now=0.0
        )
        names = [e["name"] for e in merged["entities"] if e["kind"] == "nature"]
        self.assertEqual(len(names), 3)

    def test_merge_keeps_exact_world_coordinates(self):
        self.cache.store(frame(-1, 2, [nature(-10.5, 130.25)]), tick=1)
        merged = merge_chunks(self.cache, require_all([self.cache.get(-1, 2)]), now=0.0)
        entity = merged["entities"][0]
        self.assertEqual(entity["x"], -10.5)
        self.assertEqual(entity["y"], 130.25)
        self.assertEqual(merged["origins"], [(-1, 2)])

    def test_merge_marks_partial_when_any_chunk_is_partial(self):
        self.cache.store(frame(0, 0), tick=1, now=0.0)
        self.cache.store(frame(1, 0, partial=True, chunk_complete=False), tick=1, now=0.0)
        merged = merge_chunks(
            self.cache, require_all([self.cache.get(0, 0), self.cache.get(1, 0)]), now=0.0
        )
        self.assertTrue(merged["partial"])

    def test_merge_invents_no_entities(self):
        self.cache.store(frame(0, 0, [nature(10.0, 10.0)]), tick=1)
        merged = merge_chunks(self.cache, require_all([self.cache.get(0, 0)]), now=0.0)
        self.assertEqual(len(merged["entities"]), 1)

    def test_merge_keeps_chunk_tiles_unique(self):
        tile = {"x": 0.0, "y": 0.0, "name": "grass-1"}
        self.cache.store(frame(0, 0, tiles=[tile]), tick=1)
        self.cache.store(frame(1, 0, tiles=[tile]), tick=1)
        merged = merge_chunks(
            self.cache, require_all([self.cache.get(0, 0), self.cache.get(1, 0)]), now=0.0
        )
        self.assertEqual(len(merged["tiles"]), 1)

    def test_merge_reports_the_oldest_observed_tick(self):
        self.cache.store(frame(0, 0), tick=100, now=0.0)
        self.cache.store(frame(1, 0), tick=50, now=0.0)
        merged = merge_chunks(
            self.cache, require_all([self.cache.get(0, 0), self.cache.get(1, 0)]), now=0.0
        )
        self.assertEqual(merged["oldest_tick"], 50)

    def test_merge_of_an_empty_chunk_set_invents_nothing(self):
        merged = merge_chunks(self.cache, [], now=0.0)
        self.assertEqual(merged["entities"], [])
        self.assertEqual(merged["tiles"], [])
        self.assertEqual(merged["origins"], [])


class DenseForestTests(unittest.TestCase):
    """A dense forest must be stored truthfully and stay inside the budget."""

    def test_dense_forest_with_more_than_512_entities_is_stored(self):
        cache = ChunkCache(max_chunks=4, max_age_seconds=60.0)
        cache.set_surface("nauvis")
        entities = [
            nature(index % CHUNK_TILES + 0.5, index // CHUNK_TILES + 0.5, "tree-%d" % index)
            for index in range(1200)
        ]
        cache.store(frame(0, 0, entities), tick=1)
        record = require(cache.get(0, 0))
        self.assertEqual(len(record.entities["nature"]), 1200)

    def test_entity_budget_is_enforced(self):
        cache = ChunkCache(max_chunks=2, max_age_seconds=60.0, max_entities_per_chunk=100)
        cache.set_surface("nauvis")
        entities = [nature(i + 0.5, 0.5, "tree-%d" % i) for i in range(200)]
        with self.assertRaises(ValueError):
            cache.store(frame(0, 0, entities), tick=1)

    def test_multiple_adjacent_chunks_merge_without_gaps_or_duplicates(self):
        cache = ChunkCache(max_chunks=16, max_age_seconds=60.0)
        cache.set_surface("nauvis")
        records = []
        for index in range(4):
            entities = [nature(index * CHUNK_TILES + offset + 0.5, 4.5, "tree-%d-%d" % (index, offset))
                         for offset in range(10)]
            cache.store(frame(index, 0, entities), tick=1)
            records.append(require(cache.get(index, 0)))
        merged = merge_chunks(cache, records, now=0.0)
        self.assertEqual(len(merged["origins"]), 4)
        self.assertEqual(len(merged["entities"]), 40)
        identities = {entity_identity(e) for e in merged["entities"]}
        self.assertEqual(len(identities), 40)

    def test_a_region_with_more_than_2000_entities_is_merged_truthfully(self):
        cache = ChunkCache(max_chunks=8, max_age_seconds=60.0, max_entities_per_chunk=4096)
        cache.set_surface("nauvis")
        records = []
        for index in range(4):
            entities = [
                nature(
                    index * CHUNK_TILES + (offset % CHUNK_TILES) + 0.5,
                    (offset // CHUNK_TILES) + 0.5,
                    "tree-%d-%d" % (index, offset),
                )
                for offset in range(600)
            ]
            cache.store(frame(index, 0, entities), tick=1)
            records.append(require(cache.get(index, 0)))
        merged = merge_chunks(cache, records, now=0.0)
        self.assertEqual(len(merged["entities"]), 2400)


if __name__ == "__main__":
    unittest.main()
