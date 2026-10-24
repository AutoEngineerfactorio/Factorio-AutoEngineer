"""Offline performance measurement for the R08-C multi-chunk dashboard map.

This measures the CPU-side costs the dashboard actually pays: observing a
chunk into the cache, merging the cached chunks, and answering a viewport
request. It does not measure Factorio's own read latency; the live numbers
for that come from the live acceptance run.

Scenarios required by R08-C:

* a dense forest above 512 nature entities,
* a dense region above 2000 natural entities,
* several adjacent chunks,
* a larger viewport that needs several chunk requests,
* frequent zoom and pan operations,
* a large prototype set (many distinct entity names),
* a slow backend response,
* repeated identical observations.

Every number below is produced by this script and written to
``tests/benchmark_dashboard_chunks.json``.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from dashboard_chunk_cache import ChunkCache  # noqa: E402
from dashboard_chunk_grid import CHUNK_TILES, chunks_for_viewport  # noqa: E402
from dashboard_chunk_map import merge_chunks  # noqa: E402
from dashboard_feed import encode_viewport_request  # noqa: E402

OUTPUT = ROOT / "tests" / "benchmark_dashboard_chunks.json"


def nature(index: int, name: str = "tree-01") -> dict:
    """One observed tree at a stable position inside a chunk."""
    return {
        "x": (index % CHUNK_TILES) + 0.5,
        "y": (index // CHUNK_TILES) + 0.5,
        "name": name,
        "kind": "nature",
        "entity_type": "tree",
        "prototype_type": "tree",
        "graphics_variation": index % 4,
        "map_color": {"r": 85, "g": 132, "b": 67},
    }


def terrain(chunk_x: int, chunk_y: int, entities: list[dict], partial: bool = False) -> dict:
    """One observed chunk frame."""
    return {
        "origin": {"x": chunk_x * CHUNK_TILES, "y": chunk_y * CHUNK_TILES},
        "step": 1,
        "partial": partial,
        "chunk_complete": not partial,
        "map_chunk": {"x": chunk_x, "y": chunk_y, "size": CHUNK_TILES},
        "rows": ["00" * CHUNK_TILES] * CHUNK_TILES,
        "palette": ["#000000"],
        "entities": list(entities),
    }


def timed(function, repeats: int = 20) -> dict:
    """Run a callable and report the latency distribution in milliseconds."""
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    return {
        "repeats": repeats,
        "min_ms": round(samples[0], 3),
        "mean_ms": round(statistics.fmean(samples), 3),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 3),
        "max_ms": round(samples[-1], 3),
    }


def cache_bytes(cache: ChunkCache) -> int:
    """Approximate the memory held by the cached chunks."""
    import sys as _sys

    total = 0
    for record in cache.records():
        total += _sys.getsizeof(record)
        total += _sys.getsizeof(record.entities)
        for items in record.entities.values():
            total += _sys.getsizeof(items)
            for entity in items:
                total += _sys.getsizeof(entity)
        total += _sys.getsizeof(record.terrain)
        for row in record.terrain.get("rows") or []:
            total += _sys.getsizeof(row)
    return total


def main() -> int:
    report: dict = {"chunk_tiles": CHUNK_TILES}

    # -- dense forest above 512 nature entities -------------------------
    dense = ChunkCache(max_chunks=16, max_age_seconds=300.0)
    dense.set_surface("nauvis")
    forest = [nature(i) for i in range(1200)]
    observe_ms = timed(lambda: dense.store(terrain(0, 0, forest), tick=1))
    forest_record = dense.get(0, 0)
    assert forest_record is not None
    report["dense_forest_1200"] = {
        "observe_ms": observe_ms,
        "merge_ms": timed(lambda: merge_chunks(dense, dense.records())),
        "entities": len(forest_record.entities["nature"]),
    }

    # -- dense region above 2000 natural entities across adjacent chunks --
    region = ChunkCache(max_chunks=16, max_age_seconds=300.0)
    region.set_surface("nauvis")
    region_frames = []
    for index in range(4):
        entities = [nature(i, "tree-%d" % i) for i in range(600)]
        region_frames.append((index, entities))
    for index, entities in region_frames:
        region.store(terrain(index, 0, entities), tick=1)
    report["dense_region_2400"] = {
        "observe_ms": timed(
            lambda: [region.store(terrain(i, 0, e), tick=2) for i, e in region_frames]
        ),
        "merge_ms": timed(lambda: merge_chunks(region, region.records())),
        "entities": sum(len(r.entities["nature"]) for r in region.records()),
        "chunks": len(region.records()),
    }

    # -- several adjacent chunks merged into one map ----------------------
    adjacent = ChunkCache(max_chunks=16, max_age_seconds=300.0)
    adjacent.set_surface("nauvis")
    for index in range(4):
        adjacent.store(terrain(index, 0, [nature(i) for i in range(100)]), tick=1)
    report["four_adjacent_chunks"] = {
        "merge_ms": timed(lambda: merge_chunks(adjacent, adjacent.records())),
        "chunks": len(adjacent.records()),
        "entities": sum(len(r.entities["nature"]) for r in adjacent.records()),
    }

    # -- a large viewport that needs several chunk requests ---------------
    wide = ChunkCache(max_chunks=64, max_age_seconds=300.0)
    wide.set_surface("nauvis")
    wanted = chunks_for_viewport(0.0, 0.0, 200.0, 200.0, limit=64)
    for chunk_x, chunk_y in wanted:
        wide.store(terrain(chunk_x, chunk_y, [nature(i) for i in range(50)]), tick=1)
    report["wide_viewport"] = {
        "requested_chunks": len(wanted),
        "observe_ms": timed(
            lambda: [wide.store(terrain(x, y, [nature(0)]), tick=2) for x, y in wanted]
        ),
        "merge_ms": timed(lambda: merge_chunks(wide, wide.records())),
        "cache_bytes": cache_bytes(wide),
    }
    # Revisiting the same viewport must be a cache hit, not a new request.
    wide.hits = 0
    wide.misses = 0
    revisit_start = time.perf_counter()
    for chunk_x, chunk_y in wanted:
        wide.needs_refresh(chunk_x, chunk_y)
    revisit_ms = (time.perf_counter() - revisit_start) * 1000.0
    report["wide_viewport"]["revisit_ms"] = round(revisit_ms, 3)
    report["wide_viewport"]["revisit_hit_rate"] = round(wide.stats()["hit_rate"], 4)

    # -- frequent zoom and pan: the viewport request path -----------------
    zoom_cache = ChunkCache(max_chunks=64, max_age_seconds=300.0)
    zoom_cache.set_surface("nauvis")
    zoom_views = []
    for step in range(40):
        centre = step * 64.0
        zoom_views.append(centre)
    report["zoom_pan_requests"] = {
        "encode_ms": timed(
            lambda: [encode_viewport_request(c, 0.0, 60.0, 40.0) for c in zoom_views]
        ),
        "select_ms": timed(
            lambda: [chunks_for_viewport(c, 0.0, 60.0, 40.0, limit=64) for c in zoom_views]
        ),
        "revisit_ms": timed(
            lambda: [zoom_cache.needs_refresh(x, y) for x, y in chunks_for_viewport(0.0, 0.0, 60.0, 40.0)]
        ),
    }

    # -- a large prototype set --------------------------------------------
    big = ChunkCache(max_chunks=8, max_age_seconds=300.0)
    big.set_surface("nauvis")
    prototypes = []
    for index in range(2000):
        prototypes.append(
            {
                "x": (index % CHUNK_TILES) + 0.5,
                "y": (index // CHUNK_TILES) + 0.5,
                "name": "mod-tree-%d" % index,
                "kind": "nature",
                "entity_type": "tree",
                "prototype_type": "tree",
                "map_color": {"r": index % 256, "g": (index * 7) % 256, "b": (index * 13) % 256},
            }
        )
    report["large_prototype_set"] = {
        "observe_ms": timed(lambda: big.store(terrain(0, 0, prototypes), tick=1)),
        "merge_ms": timed(lambda: merge_chunks(big, big.records())),
        "distinct_prototypes": len({e["name"] for e in prototypes}),
    }

    # -- a slow backend response ------------------------------------------
    def slow_observation():
        time.sleep(0.02)
        slow_cache.store(terrain(1, 1, [nature(0)]), tick=1)

    slow_cache = ChunkCache(max_chunks=8, max_age_seconds=300.0)
    slow_cache.set_surface("nauvis")
    report["slow_backend_20ms"] = {
        "observe_ms": timed(slow_observation, repeats=10),
        "note": "The slow response is outside the cache; the cache cost is "
        "the remainder after the simulated backend delay.",
    }

    # -- repeated identical observations ----------------------------------
    repeat = ChunkCache(max_chunks=8, max_age_seconds=300.0)
    repeat.set_surface("nauvis")
    repeat.store(terrain(0, 0, [nature(i) for i in range(200)]), tick=1)
    report["repeated_identical_observation"] = {
        "observe_ms": timed(lambda: repeat.store(terrain(0, 0, [nature(i) for i in range(200)]), tick=1)),
        "merge_ms": timed(lambda: merge_chunks(repeat, repeat.records())),
        "cache_bytes": cache_bytes(repeat),
    }

    # -- memory bound ------------------------------------------------------
    bounded = ChunkCache(max_chunks=8, max_age_seconds=300.0)
    bounded.set_surface("nauvis")
    for index in range(64):
        bounded.store(terrain(index, 0, [nature(0)]), tick=index)
    report["memory_bound"] = {
        "max_chunks": bounded.max_chunks,
        "cached_chunks": len(bounded.records()),
        "cache_bytes": cache_bytes(bounded),
    }

    # -- partial chunk reporting ------------------------------------------
    partial_cache = ChunkCache(max_chunks=8, max_age_seconds=300.0)
    partial_cache.set_surface("nauvis")
    partial_cache.store(terrain(0, 0, [nature(0)], partial=True), tick=1)
    stats = partial_cache.stats()
    report["partial_reporting"] = {
        "partial_chunks": stats["partial"],
        "fresh_chunks": stats["fresh"],
        "stale_chunks": stats["stale"],
        "merged_partial": merge_chunks(partial_cache, partial_cache.records())["partial"],
    }

    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("WROTE=" + str(OUTPUT))
    for key, value in report.items():
        if isinstance(value, dict):
            print(key + "=" + json.dumps(value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
