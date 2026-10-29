"""Integration tests for the R08-C multi-chunk dashboard map pipeline.

These cover the path a real viewport takes: the dashboard encodes a viewport
request, the observer turns it into bounded chunk requests and supersedes an
obsolete one, and the observer publishes a merged map that the dashboard
renders and the frame parser accepts.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

from dashboard_chunk_cache import ChunkCache  # noqa: E402
from dashboard_chunk_grid import CHUNK_TILES, chunk_origin  # noqa: E402
from dashboard_feed import (  # noqa: E402
    PREFIX,
    VIEWPORT_PREFIX,
    DashboardFeed,
    decode_viewport_request,
    encode_viewport_request,
    parse_frame,
)
from dashboard_observer import (  # noqa: E402
    ViewportRequests,
    chunk_arguments,
    observe_viewport,
)


def chunk_frame(chunk_x=0, chunk_y=0, entities=(), tick=1, partial=False, chunk_complete=True):
    """Build a complete backend frame that observes one aligned chunk."""
    origin = chunk_origin(chunk_x, chunk_y)
    return {
        "status": "ok",
        "x": origin["x"] + 1.0,
        "y": origin["y"] + 1.0,
        "tick": tick,
        "surface": "nauvis",
        "inventory": [],
        "inventory_available": True,
        "truncated": False,
        "slots": [],
        "capacity": 0,
        "slots_truncated": False,
        "terrain": {
            "origin": {"x": origin["x"], "y": origin["y"]},
            "step": 1,
            "partial": partial,
            "chunk_complete": chunk_complete,
            "map_chunk": {"x": chunk_x, "y": chunk_y, "size": CHUNK_TILES},
            "rows": ["00" * CHUNK_TILES] * CHUNK_TILES,
            "palette": ["#000000"],
            "entities": list(entities),
        },
    }


def nature(x, y, name="tree-01"):
    return {"x": x, "y": y, "name": name, "kind": "nature"}


class ViewportProtocolTests(unittest.TestCase):
    def test_encoded_request_round_trips(self):
        line = encode_viewport_request(12.5, -8.0, 60.0, 40.0)
        self.assertTrue(line.startswith(VIEWPORT_PREFIX))
        request = decode_viewport_request(line)
        if request is None:
            self.fail("encoded viewport request did not decode")
        self.assertEqual(request["center"], {"x": 12.5, "y": -8.0})
        self.assertEqual(request["radius"], {"x": 60.0, "y": 40.0})
        self.assertEqual(request["schema"], 1)

    def test_decoding_a_non_request_returns_none(self):
        self.assertIsNone(decode_viewport_request("hello"))
        self.assertIsNone(decode_viewport_request(""))

    def test_malformed_requests_are_rejected(self):
        for payload in (
            "{",
            "[]",
            '{"schema":2,"center":{"x":0,"y":0},"radius":{"x":1,"y":1},"limit":8}',
            '{"schema":1,"center":{"x":0},"radius":{"x":1,"y":1},"limit":8}',
            '{"schema":1,"center":{"x":0,"y":0},"radius":{"x":-1,"y":1},"limit":8}',
            '{"schema":1,"center":{"x":0,"y":0},"radius":{"x":1,"y":1},"limit":0}',
            '{"schema":1,"center":{"x":0,"y":0},"radius":{"x":1,"y":1},"limit":9999}',
            '{"schema":1,"center":{"x":"a","y":0},"radius":{"x":1,"y":1},"limit":8}',
        ):
            with self.assertRaises(ValueError):
                decode_viewport_request(VIEWPORT_PREFIX + payload)

    def test_encoding_rejects_invalid_bounds(self):
        for args in (
            (float("inf"), 0.0, 1.0, 1.0),
            (0.0, float("nan"), 1.0, 1.0),
            (0.0, 0.0, -1.0, 1.0),
            (1e9, 0.0, 1.0, 1.0),
            ("a", 0.0, 1.0, 1.0),
        ):
            with self.assertRaises(ValueError):
                encode_viewport_request(*args)

    def test_oversized_request_line_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_viewport_request(VIEWPORT_PREFIX + "x" * 5000)


class ViewportRequestChannelTests(unittest.TestCase):
    def test_the_latest_request_wins(self):
        requests = ViewportRequests()
        requests.read_line(encode_viewport_request(0.0, 0.0, 10.0, 10.0))
        requests.read_line(encode_viewport_request(100.0, 0.0, 10.0, 10.0))
        latest = requests.take()
        assert latest is not None
        self.assertEqual(latest["center"], {"x": 100.0, "y": 0.0})
        self.assertIsNone(requests.take())

    def test_a_malformed_request_is_ignored_and_keeps_the_previous_one(self):
        requests = ViewportRequests()
        requests.read_line(encode_viewport_request(0.0, 0.0, 10.0, 10.0))
        requests.read_line(VIEWPORT_PREFIX + "{broken")
        latest = requests.take()
        assert latest is not None
        self.assertEqual(latest["center"], {"x": 0.0, "y": 0.0})

    def test_a_non_request_line_is_not_consumed(self):
        requests = ViewportRequests()
        self.assertFalse(requests.read_line("q\n"))
        self.assertIsNone(requests.take())

    def test_backend_chunk_arguments_are_bounded_integers(self):
        """The chunk arguments name the chunk and skip the recipe catalog.

        A map chunk never needs the recipe catalog, so the request asks
        for the fast path. The backend then does not enumerate any recipe,
        recompute the technology fingerprint or enumerate any machine
        prototype.
        """
        self.assertEqual(
            chunk_arguments(-3, 7),
            {"mapChunkX": -3, "mapChunkY": 7, "noCatalog": True}
        )


class FeedCachePublishingTests(unittest.TestCase):
    def test_the_feed_stores_the_observed_chunk(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        feed.remember(chunk_frame(0, 0, [nature(1.0, 2.0)]))
        self.assertIsNotNone(feed.cache.get(0, 0))

    def test_the_published_map_contains_the_observed_entities(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        merged = feed.remember(chunk_frame(0, 0, [nature(1.0, 2.0)]))
        self.assertEqual(len(merged["entities"]), 1)
        self.assertEqual(merged["origins"], [(0, 0)])
        self.assertFalse(merged["partial"])

    def test_two_chunks_merge_into_one_map_without_duplicates(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        shared = nature(64.0, 10.0)
        feed.remember(chunk_frame(0, 0, [nature(10.0, 10.0), shared]))
        merged = feed.remember(chunk_frame(1, 0, [shared, nature(70.0, 10.0)]))
        self.assertEqual(len(merged["origins"]), 2)
        self.assertEqual(len(merged["entities"]), 3)

    def test_a_partial_chunk_marks_the_merged_map_partial(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        merged = feed.remember(
            chunk_frame(0, 0, partial=True, chunk_complete=False)
        )
        self.assertTrue(merged["partial"])

    def test_switching_surface_isolates_the_cached_chunks(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        feed.remember(chunk_frame(0, 0))
        self.assertIsNotNone(feed.cache.get(0, 0))
        other = dict(chunk_frame(0, 0))
        other["surface"] = "vulcanus"
        merged = feed.remember(other)
        # The nauvis chunk is gone; only the vulcanus observation remains.
        self.assertEqual(feed.cache.surface, "vulcanus")
        record = feed.cache.get(0, 0)
        assert record is not None
        self.assertEqual(record.surface, "vulcanus")
        self.assertEqual(merged["surface"], "vulcanus")

    def test_a_frame_without_chunk_metadata_is_not_stored(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        frame = chunk_frame(0, 0)
        del frame["terrain"]["map_chunk"]
        merged = feed.remember(frame)
        self.assertEqual(merged["origins"], [])
        self.assertEqual(merged["entities"], [])

    def test_the_map_statistics_report_the_cached_chunks(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        merged = feed.remember(chunk_frame(0, 0))
        self.assertEqual(merged["stats"]["chunks"], 1)
        self.assertEqual(merged["stats"]["surface"], "nauvis")


class FrameRoundTripTests(unittest.TestCase):
    @staticmethod
    def publishable_frame(terrain, merged=None):
        """Build a frame shaped like the one the observer publishes."""
        frame = {
            "schema": 1,
            "status": "ok",
            "position": {"x": 1.0, "y": 1.0},
            "tick": 1,
            "surface": "nauvis",
            "telemetry": {
                "schema": 1,
                "tick": 1,
                "production": {
                    "status": "unavailable",
                    "reason": "Backend does not report production telemetry",
                    "items": {
                        "status": "unavailable",
                        "reason": "Backend does not report item flow statistics",
                    },
                    "fluids": {
                        "status": "unavailable",
                        "reason": "Backend does not report fluid flow statistics",
                    },
                },
                "power": {
                    "status": "unavailable",
                    "reason": "Backend does not report power telemetry",
                    "unit": "joules_per_tick",
                    "tick": 1,
                    "networks": [],
                    "partial": False,
                },
            },
            "inventory": [],
            "inventory_available": True,
            "truncated": False,
            "slots": [],
            "capacity": 0,
            "slots_truncated": False,
            "terrain": terrain,
            "visited": [],
            "failed": [],
            "resources": [],
            "objective": None,
            "proposal": None,
            "resource_age_seconds": None,
        }
        if merged is not None:
            frame["map"] = merged
        return frame

    def test_the_published_frame_survives_the_frame_parser(self):
        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        feed.remember(chunk_frame(0, 0, [nature(1.0, 2.0)]))
        merged = feed.merged_map()
        frame = self.publishable_frame(chunk_frame(0, 0)["terrain"], merged)
        parsed = parse_frame(PREFIX + __import__("json").dumps(frame))
        assert parsed is not None and parsed["map"] is not None
        self.assertEqual(len(parsed["map"]["entities"]), 1)
        self.assertEqual(parsed["map"]["origins"], [(0, 0)])

    def test_a_frame_without_a_map_still_parses(self):
        frame = self.publishable_frame(chunk_frame(0, 0)["terrain"])
        parsed = parse_frame(PREFIX + __import__("json").dumps(frame))
        assert parsed is not None
        self.assertIsNone(parsed["map"])

    def test_a_malformed_map_is_rejected(self):
        frame = self.publishable_frame(
            chunk_frame(0, 0)["terrain"],
            {"entities": [{"x": 1.0, "y": 2.0, "kind": "execute"}]},
        )
        with self.assertRaises(ValueError):
            parse_frame(PREFIX + __import__("json").dumps(frame))


class ObserverViewportTests(unittest.TestCase):
    """The observer must request only what the viewport needs."""

    @staticmethod
    def quiet(feed, session, control, requests):
        """Run the observer viewport step without printing published frames."""
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            asyncio.run(observe_viewport(session, feed, control, requests))

    def test_the_observer_requests_the_missing_chunks_of_the_viewport(self):
        observed = []

        class FakeSession:
            async def call_tool(self, name, arguments=None):
                observed.append(dict(arguments or {}))
                chunk_x = (arguments or {}).get("mapChunkX", 0)
                chunk_y = (arguments or {}).get("mapChunkY", 0)
                return _FakeResponse(chunk_frame(chunk_x, chunk_y))

        class Control:
            class _Stop:
                def is_set(self):
                    return False

            stop = _Stop()

        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        requests = ViewportRequests()
        requests.read_line(encode_viewport_request(0.0, 0.0, 10.0, 10.0))
        self.quiet(feed, FakeSession(), Control(), requests)
        self.assertTrue(observed)
        for call in observed:
            self.assertIn("mapChunkX", call)
            self.assertIn("mapChunkY", call)

    def test_an_already_observed_chunk_is_not_requested_again(self):
        observed = []

        class FakeSession:
            async def call_tool(self, name, arguments=None):
                observed.append(dict(arguments or {}))
                return _FakeResponse(chunk_frame(0, 0))

        class Control:
            class _Stop:
                def is_set(self):
                    return False

            stop = _Stop()

        feed = DashboardFeed(cache=ChunkCache(max_chunks=8, max_age_seconds=60.0))
        # The viewport at the origin touches four chunks; cache all of them.
        for chunk_x, chunk_y in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
            feed.remember(chunk_frame(chunk_x, chunk_y))
        requests = ViewportRequests()
        requests.read_line(encode_viewport_request(0.0, 0.0, 10.0, 10.0))
        self.quiet(feed, FakeSession(), Control(), requests)
        self.assertEqual(observed, [])


class _FakeResponse:
    """Minimal stand-in for an MCP tool response."""

    def __init__(self, payload):
        self.is_error = False
        self.content = [_FakeText(__import__("json").dumps(payload))]


class _FakeText:
    def __init__(self, text):
        self.type = "text"
        self.text = text


if __name__ == "__main__":
    unittest.main()
