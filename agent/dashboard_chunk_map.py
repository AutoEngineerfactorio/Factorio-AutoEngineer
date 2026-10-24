"""Assemble cached map chunks into one continuous dashboard map.

This module turns a set of observed chunk records into a single map
description the view can draw. It never invents content:

* A tile or entity appears only if an observed chunk reported it.
* An entity that two adjacent chunks both report is emitted once, so a
  shared chunk boundary cannot produce a duplicated tree.
* A chunk that was only partially observed keeps the merged map marked
  ``partial`` so the view can show it differently from a complete one.
* A chunk that aged out is reported as ``stale``; the merged map keeps the
  historical observation but never claims it is current.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from dashboard_chunk_grid import ENTITY_KINDS, chunk_key, chunk_origin


def entity_identity(entity: dict[str, Any]) -> tuple:
    """Return a stable identity for an observed entity.

    Two observations of the same entity produce the same identity, which is
    what keeps a merged map free of duplicates where two chunks meet.
    """
    return (
        entity.get("kind"),
        entity.get("name"),
        round(float(entity.get("x", 0.0)), 3),
        round(float(entity.get("y", 0.0)), 3),
    )


def require(record: "ChunkRecord | None") -> "ChunkRecord":
    """Return the record or raise, for callers that expect a cached chunk."""
    if record is None:
        raise KeyError("Chunk is not cached")
    return record


def require_all(records: "list[ChunkRecord | None]") -> "list[ChunkRecord]":
    """Return every record or raise, for a batch of expected chunks."""
    return [require(record) for record in records]


@dataclass
class ChunkRecord:
    """One observed chunk and everything the cache knows about it."""

    surface: str
    chunk_x: int
    chunk_y: int
    tick: int
    observed_at: float
    partial: bool = False
    chunk_complete: bool = True
    terrain: dict[str, Any] = field(default_factory=dict)
    entities: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    overlays: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, int, int]:
        return chunk_key(self.surface, self.chunk_x, self.chunk_y)

    @property
    def origin(self) -> dict[str, float]:
        return chunk_origin(self.chunk_x, self.chunk_y)

    def entity_count(self) -> int:
        return sum(len(items) for items in self.entities.values())

    def is_stale(self, now: float, max_age_seconds: float) -> bool:
        """Return True when the observation is older than the policy allows."""
        if max_age_seconds <= 0:
            return True
        return (now - self.observed_at) > max_age_seconds

    def status(self, now: float, max_age_seconds: float) -> str:
        """Return the truthful display status of this chunk.

        ``unobserved`` is never returned here: an unobserved chunk has no
        record at all. ``partial`` outranks ``stale``: an incomplete
        observation stays incomplete even when it also ages.
        """
        if not self.chunk_complete or self.partial:
            return "partial"
        if self.is_stale(now, max_age_seconds):
            return "stale"
        return "fresh"


def merge_chunks(cache, chunks: Iterable[Any], now: float | None = None) -> dict[str, Any]:
    """Merge observed chunk records into one continuous map description.

    ``cache`` supplies the surface name and the freshness policy.
    """
    moment = time.monotonic() if now is None else now
    entities: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    origins: list[tuple[int, int]] = []
    tiles: list[dict[str, Any]] = []
    seen_tiles: set[tuple] = set()
    statuses: list[str] = []
    rasters: list[dict[str, Any]] = []
    partial = False
    oldest_tick = None
    for record in chunks:
        origins.append((record.chunk_x, record.chunk_y))
        status = record.status(moment, cache.max_age_seconds)
        statuses.append(status)
        if status == "partial":
            partial = True
        if oldest_tick is None or record.tick < oldest_tick:
            oldest_tick = record.tick
        for kind in ENTITY_KINDS:
            for entity in record.entities.get(kind, []):
                identity = entity_identity(entity)
                if identity in seen:
                    continue
                seen.add(identity)
                entities.append(dict(entity))
        if record.terrain.get("rows") and record.terrain.get("palette"):
            rasters.append({
                "origin": dict(record.origin),
                "rows": list(record.terrain["rows"]),
                "palette": list(record.terrain["palette"]),
            })
        for tile in record.terrain.get("tiles") or []:
            if not isinstance(tile, dict):
                continue
            marker = (tile.get("x"), tile.get("y"))
            if marker in seen_tiles:
                continue
            seen_tiles.add(marker)
            tiles.append(dict(tile))
    origins.sort()
    return {
        "surface": cache.surface,
        "origins": origins,
        "tiles": tiles,
        "rasters": rasters,
        "entities": entities,
        "partial": partial,
        "oldest_tick": oldest_tick,
        "statuses": statuses,
    }


def cache_stats(cache, now: float | None = None) -> dict[str, Any]:
    """Return bounded cache statistics for the dashboard status line."""
    moment = time.monotonic() if now is None else now
    fresh = stale = partial = 0
    for record in cache.records():
        status = record.status(moment, cache.max_age_seconds)
        if status == "partial":
            partial += 1
        elif status == "stale":
            stale += 1
        else:
            fresh += 1
    total = cache.hits + cache.misses
    return {
        "surface": cache.surface,
        "chunks": len(cache.records()),
        "max_chunks": cache.max_chunks,
        "fresh": fresh,
        "stale": stale,
        "partial": partial,
        "requests": cache.requests,
        "hits": cache.hits,
        "misses": cache.misses,
        "hit_rate": (cache.hits / total) if total else 0.0,
        "entities": sum(record.entity_count() for record in cache.records()),
        "generation": cache.generation,
    }
