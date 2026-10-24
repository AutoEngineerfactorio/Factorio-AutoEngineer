"""Offline tests for the read-only dashboard multi-chunk map cache."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

from dashboard_chunk_cache import ChunkCache  # noqa: E402
from dashboard_chunk_grid import CHUNK_TILES, chunk_origin  # noqa: E402
from dashboard_chunk_map import entity_identity, require  # noqa: E402


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


class ChunkCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = ChunkCache(max_chunks=4, max_age_seconds=60.0)
        self.cache.set_surface("nauvis")

    def test_store_requires_chunk_metadata(self):
        with self.assertRaises(ValueError):
            self.cache.store({"origin": {"x": 0, "y": 0}}, tick=1)

    def test_store_rejects_misaligned_origin(self):
        bad = frame(0, 0)
        bad["origin"] = {"x": 3, "y": 0}
        with self.assertRaises(ValueError):
            self.cache.store(bad, tick=1)

    def test_store_and_retrieve_preserves_world_coordinates(self):
        self.cache.store(frame(2, -1, [nature(128.5, -64.25)]), tick=10)
        record = require(self.cache.get(2, -1))
        self.assertEqual(record.origin, {"x": 128, "y": -64})
        self.assertEqual(record.entities["nature"][0]["x"], 128.5)
        self.assertEqual(record.entities["nature"][0]["y"], -64.25)

    def test_unobserved_chunk_is_absent_not_empty(self):
        self.assertIsNone(self.cache.get(9, 9))
        self.assertTrue(self.cache.needs_refresh(9, 9))

    def test_partial_chunk_never_becomes_complete(self):
        self.cache.store(frame(0, 0, partial=True, chunk_complete=False), tick=1)
        record = require(self.cache.get(0, 0))
        self.assertFalse(record.chunk_complete)
        self.assertTrue(record.partial)
        self.assertEqual(record.status(0.0, 60.0), "partial")
        # A later complete observation of the same chunk is a new record.
        self.cache.store(frame(0, 0, partial=False, chunk_complete=True), tick=2)
        record = require(self.cache.get(0, 0))
        self.assertTrue(record.chunk_complete)
        self.assertEqual(record.status(0.0, 60.0), "fresh")

    def test_partial_flag_without_completeness_is_not_certified_complete(self):
        payload = frame(0, 0)
        del payload["chunk_complete"]
        self.cache.store(payload, tick=1)
        record = require(self.cache.get(0, 0))
        self.assertTrue(record.chunk_complete)

    def test_stale_chunk_is_reported_and_needs_refresh(self):
        self.cache.store(frame(0, 0), tick=1, now=1000.0)
        record = require(self.cache.get(0, 0))
        self.assertEqual(record.status(1000.0, 60.0), "fresh")
        self.assertEqual(record.status(1200.0, 60.0), "stale")
        self.assertTrue(self.cache.needs_refresh(0, 0, now=1200.0))
        self.assertFalse(self.cache.needs_refresh(0, 0, now=1010.0))

    def test_surface_change_isolates_the_cache(self):
        self.cache.store(frame(0, 0), tick=1)
        self.assertIsNotNone(self.cache.get(0, 0))
        self.cache.set_surface("vulcanus")
        self.assertIsNone(self.cache.get(0, 0))
        self.assertEqual(self.cache.stats()["surface"], "vulcanus")

    def test_same_surface_does_not_clear_the_cache(self):
        self.cache.store(frame(0, 0), tick=1)
        generation = self.cache.generation
        self.cache.set_surface("nauvis")
        self.assertIsNotNone(self.cache.get(0, 0))
        self.assertEqual(self.cache.generation, generation)

    def test_reset_clears_every_chunk_for_a_game_restart(self):
        self.cache.store(frame(0, 0), tick=1)
        generation = self.cache.generation
        self.cache.reset()
        self.assertIsNone(self.cache.get(0, 0))
        self.assertGreater(self.cache.generation, generation)

    def test_memory_budget_evicts_the_least_recently_used_chunk(self):
        for index in range(5):
            self.cache.store(frame(index, 0), tick=index)
        self.assertLessEqual(self.cache.stats()["chunks"], 4)
        self.assertIsNone(self.cache.get(0, 0))
        self.assertIsNotNone(self.cache.get(4, 0))

    def test_duplicate_entities_within_one_frame_are_stored_once(self):
        self.cache.store(frame(0, 0, [nature(1.0, 2.0), nature(1.0, 2.0)]), tick=1)
        record = require(self.cache.get(0, 0))
        self.assertEqual(len(record.entities["nature"]), 1)

    def test_entity_identity_is_stable_and_distinguishing(self):
        one = nature(10.0, 20.0)
        two = nature(10.0, 20.0)
        three = nature(10.5, 20.0)
        self.assertEqual(entity_identity(one), entity_identity(two))
        self.assertNotEqual(entity_identity(one), entity_identity(three))

    def test_stats_report_hit_and_miss_rate(self):
        self.cache.store(frame(0, 0), tick=1)
        self.cache.get(0, 0)
        self.cache.get(5, 5)
        stats = self.cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hit_rate"], 0.5)

    def test_stats_count_partial_and_stale_separately(self):
        self.cache.store(frame(0, 0), tick=1, now=0.0)
        self.cache.store(frame(1, 0, partial=True, chunk_complete=False), tick=1, now=0.0)
        self.cache.store(frame(2, 0), tick=1, now=0.0)
        stats = self.cache.stats(now=1000.0)
        self.assertEqual(stats["partial"], 1)
        self.assertEqual(stats["stale"], 2)
        self.assertEqual(stats["fresh"], 0)

    def test_store_rejects_an_invalid_tick(self):
        for bad in (-1, 1.5, True, "5"):
            with self.assertRaises(ValueError):
                self.cache.store(frame(0, 0), tick=bad)  # type: ignore[arg-type]

    def test_store_rejects_an_invalid_entity_kind(self):
        bad = frame(0, 0, [{"x": 1.0, "y": 2.0, "name": "x", "kind": "unknown"}])
        with self.assertRaises(ValueError):
            self.cache.store(bad, tick=1)


if __name__ == "__main__":
    unittest.main()
