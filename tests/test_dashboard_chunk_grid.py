"""Offline tests for the read-only dashboard map-chunk grid."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

from dashboard_chunk_grid import (  # noqa: E402
    CHUNK_TILES,
    chunk_key,
    chunk_of,
    chunk_origin,
    chunks_for_viewport,
    validate_chunk_request,
)


class ChunkAlignmentTests(unittest.TestCase):
    def test_chunk_of_floors_towards_negative_infinity(self):
        self.assertEqual(chunk_of(0, 0), (0, 0))
        self.assertEqual(chunk_of(63.9, 63.9), (0, 0))
        self.assertEqual(chunk_of(64, 64), (1, 1))
        self.assertEqual(chunk_of(-0.1, -0.1), (-1, -1))
        self.assertEqual(chunk_of(-64, -64), (-1, -1))
        self.assertEqual(chunk_of(-64.1, -64.1), (-2, -2))

    def test_chunk_origin_is_aligned(self):
        self.assertEqual(chunk_origin(0, 0), {"x": 0, "y": 0})
        self.assertEqual(chunk_origin(-2, 3), {"x": -128, "y": 192})
        for chunk_x in (-3, 0, 7):
            for chunk_y in (-5, 0, 11):
                origin = chunk_origin(chunk_x, chunk_y)
                self.assertEqual(origin["x"] % CHUNK_TILES, 0)
                self.assertEqual(origin["y"] % CHUNK_TILES, 0)

    def test_chunk_key_is_surface_scoped(self):
        self.assertNotEqual(chunk_key("nauvis", 1, 1), chunk_key("vulcanus", 1, 1))

    def test_chunk_request_validation_rejects_malformed_input(self):
        for bad in (
            (0,),
            (0, 1, 2),
            "0,1",
            None,
            (True, 0),
            (0, False),
            (1.5, 0),
            ("0", 0),
            (0, "1"),
            (100001, 0),
            (0, -100001),
        ):
            with self.assertRaises(ValueError):
                validate_chunk_request(bad)

    def test_chunk_request_validation_accepts_bounded_integers(self):
        self.assertEqual(validate_chunk_request((-5, 7)), (-5, 7))
        self.assertEqual(validate_chunk_request([0, 0]), (0, 0))
        self.assertEqual(validate_chunk_request((100000, -100000)), (100000, -100000))


class ViewportChunkTests(unittest.TestCase):
    """A viewport must select a bounded, prioritised set of chunks."""

    def test_viewport_selects_the_chunks_it_touches(self):
        # A radius of 10 around the origin spans x and y in [-10, 10], which
        # floors into four chunks because the grid floors towards -infinity.
        chunks = chunks_for_viewport(0.0, 0.0, 10.0, 10.0)
        self.assertEqual(chunks, [(0, 0), (0, -1), (-1, 0), (-1, -1)])

    def test_viewport_selects_adjacent_chunks_when_panned(self):
        chunks = chunks_for_viewport(100.0, 0.0, 10.0, 10.0)
        self.assertEqual(chunks, [(1, 0), (1, -1)])

    def test_viewport_prioritises_the_centre_chunk_first(self):
        chunks = chunks_for_viewport(0.0, 0.0, 200.0, 200.0)
        self.assertEqual(chunks[0], (0, 0))

    def test_viewport_chunk_count_is_bounded(self):
        chunks = chunks_for_viewport(0.0, 0.0, 4000.0, 4000.0, limit=8)
        self.assertEqual(len(chunks), 8)

    def test_viewport_rejects_an_invalid_limit(self):
        for bad in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                chunks_for_viewport(0.0, 0.0, 10.0, 10.0, limit=bad)  # type: ignore[arg-type]

    def test_viewport_rejects_non_finite_bounds(self):
        with self.assertRaises(ValueError):
            chunks_for_viewport(float("inf"), 0.0, 10.0, 10.0)

    def test_zoomed_in_viewport_needs_fewer_chunks_than_zoomed_out(self):
        near = chunks_for_viewport(0.0, 0.0, 10.0, 10.0)
        far = chunks_for_viewport(0.0, 0.0, 300.0, 300.0)
        self.assertLess(len(near), len(far))

    def test_viewport_never_returns_the_same_chunk_twice(self):
        chunks = chunks_for_viewport(64.0, 64.0, 200.0, 200.0, limit=32)
        self.assertEqual(len(chunks), len(set(chunks)))


if __name__ == "__main__":
    unittest.main()
