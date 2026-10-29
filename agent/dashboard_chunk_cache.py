"""Multi-chunk map cache for the read-only AutoEngineer dashboard.

The dashboard map is assembled from many observed 64x64 world chunks instead
of a single window around the player. This module owns that storage.

Truthfulness rules enforced here:

* Only data the observer actually reported is stored. Nothing is inferred
  from a prototype name, a neighbouring chunk or a resource patch.
* A chunk that could not be fully observed stays ``partial``. A partial chunk
  never becomes complete because a later frame happened to be complete.
* A cached chunk never claims that an entity it saw earlier is still there.
  The cache distinguishes the *observation* (a historical record of what was
  seen at a tick) from the *current* entity set.
* Chunks from one surface are never served for another surface.
* Unobserved chunks are simply absent. The map layer keeps them unobserved.
"""
from __future__ import annotations

import math
import time
from collections import OrderedDict
from typing import Any, Iterable

from dashboard_chunk_grid import (
    CHUNK_TILES,
    ENTITY_KINDS,
    chunk_key,
    chunk_origin,
    validate_chunk_request,
)
from dashboard_chunk_map import ChunkRecord, entity_identity, require, require_all

__all__ = [
    "CHUNK_TILES",
    "ChunkCache",
    "ChunkRecord",
    "entity_identity",
    "require",
    "require_all",
]


#: The default number of chunks the cache holds.
DEFAULT_MAX_CHUNKS = 64

#: The default lifetime of one cached chunk, in seconds.
DEFAULT_MAX_AGE_SECONDS = 300.0


def _configured_cache_limits() -> tuple[int, float]:
    """Return the chunk count and the chunk lifetime from the settings.

    A missing or unusable setting falls back to the protective default,
    so the cache can never become unbounded because of a setting.
    """
    try:
        from cache_context import limits

        entries, ttl = limits()
    except Exception:
        return DEFAULT_MAX_CHUNKS, DEFAULT_MAX_AGE_SECONDS
    return max(1, entries), float(ttl)


class ChunkCache:
    """Bounded, surface-scoped cache of observed map chunks."""

    def __init__(
        self,
        max_chunks: int | None = None,
        max_age_seconds: float | None = None,
        max_entities_per_chunk: int = 4096,
    ) -> None:
        if max_chunks is None or max_age_seconds is None:
            configured_entries, configured_ttl = _configured_cache_limits()
            if max_chunks is None:
                max_chunks = configured_entries
            if max_age_seconds is None:
                max_age_seconds = configured_ttl
        if type(max_chunks) is not int or max_chunks < 1:
            raise ValueError("Chunk budget must be a positive integer")
        if not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("Chunk age limit must be positive")
        if type(max_entities_per_chunk) is not int or max_entities_per_chunk < 1:
            raise ValueError("Entity budget must be a positive integer")
        self.max_chunks = max_chunks
        self.max_age_seconds = max_age_seconds
        self.max_entities_per_chunk = max_entities_per_chunk
        self._chunks: "OrderedDict[tuple[str, int, int], ChunkRecord]" = OrderedDict()
        self._surface: str | None = None
        self._generation = 0
        self.hits = 0
        self.misses = 0
        self.requests = 0

    # -- surface handling -------------------------------------------------

    @property
    def surface(self) -> str | None:
        """The surface the cached chunks belong to."""
        return self._surface

    def set_surface(self, surface: str) -> None:
        """Switch the cache to a surface.

        A different surface isolates the cache completely: the previous
        surface's chunks are dropped so they can never be drawn as if they
        belonged to the new surface.
        """
        if not isinstance(surface, str) or not 1 <= len(surface) <= 128:
            raise ValueError("Invalid surface name")
        if surface == self._surface:
            return
        self._surface = surface
        self._invalidate()

    def reset(self) -> None:
        """Drop every cached chunk, for example after a game restart."""
        self._invalidate()

    def _invalidate(self) -> None:
        """Clear the cached chunks and the request counters."""
        self._chunks.clear()
        self._generation += 1
        self.hits = 0
        self.misses = 0
        self.requests = 0

    @property
    def generation(self) -> int:
        """Counter that changes whenever the cached content is invalidated."""
        return self._generation

    # -- observation intake ----------------------------------------------

    def store(self, terrain: dict[str, Any], tick: int, now: float | None = None) -> ChunkRecord:
        """Store one observed chunk frame.

        The frame must carry chunk metadata. A frame without it comes from an
        older backend and cannot be placed on the chunk grid, so it is
        rejected rather than guessed at.
        """
        if not isinstance(terrain, dict):
            raise ValueError("Invalid terrain frame")
        chunk = terrain.get("map_chunk")
        if not isinstance(chunk, dict):
            raise ValueError("Terrain frame has no map chunk metadata")
        chunk_x, chunk_y = validate_chunk_request((chunk.get("x"), chunk.get("y")))
        if chunk.get("size") != CHUNK_TILES:
            raise ValueError("Unexpected map chunk size")
        origin = terrain.get("origin")
        if not isinstance(origin, dict):
            raise ValueError("Terrain frame has no origin")
        expected = chunk_origin(chunk_x, chunk_y)
        if origin.get("x") != expected["x"] or origin.get("y") != expected["y"]:
            raise ValueError("Terrain origin does not match its chunk")
        if type(tick) is not int or tick < 0:
            raise ValueError("Invalid observation tick")
        surface = self._surface
        if surface is None:
            raise ValueError("Cache has no surface")

        entities: dict[str, list[dict[str, Any]]] = {kind: [] for kind in ENTITY_KINDS}
        seen: set[tuple] = set()
        for entity in terrain.get("entities") or []:
            if not isinstance(entity, dict):
                raise ValueError("Invalid observed entity")
            kind = entity.get("kind")
            if kind not in ENTITY_KINDS:
                raise ValueError("Invalid observed entity kind")
            identity = entity_identity(entity)
            if identity in seen:
                # The same entity reported twice in one frame is one entity.
                continue
            seen.add(identity)
            entities[kind].append(dict(entity))

        total = sum(len(items) for items in entities.values())
        if total > self.max_entities_per_chunk:
            raise ValueError("Observed chunk exceeds the entity budget")

        partial = bool(terrain.get("partial"))
        chunk_complete = terrain.get("chunk_complete")
        if chunk_complete is None:
            # An older backend reported only ``partial``. Without an explicit
            # completeness flag the observation cannot be certified complete.
            chunk_complete = not partial
        if type(chunk_complete) is not bool:
            raise ValueError("Invalid chunk completeness flag")
        if partial:
            chunk_complete = False

        record = ChunkRecord(
            surface=surface,
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            tick=tick,
            observed_at=time.monotonic() if now is None else now,
            partial=partial,
            chunk_complete=chunk_complete,
            terrain=dict(terrain),
            entities=entities,
            overlays=dict(terrain.get("overlays") or {}),
        )
        key = record.key
        self._chunks.pop(key, None)
        self._chunks[key] = record
        self._evict()
        return record

    def _evict(self) -> None:
        """Drop the least recently used chunks until the budget fits."""
        while len(self._chunks) > self.max_chunks:
            self._chunks.popitem(last=False)

    # -- retrieval ---------------------------------------------------------

    def records(self) -> list[ChunkRecord]:
        """Return every cached record, oldest first."""
        return list(self._chunks.values())

    def get(self, chunk_x: int, chunk_y: int) -> ChunkRecord | None:
        """Return a cached chunk, or None when it was never observed."""
        chunk_x, chunk_y = validate_chunk_request((chunk_x, chunk_y))
        if self._surface is None:
            return None
        record = self._chunks.get(chunk_key(self._surface, chunk_x, chunk_y))
        if record is None:
            self.misses += 1
            return None
        self._chunks.move_to_end(record.key)
        self.hits += 1
        return record

    def is_fresh(self, chunk_x: int, chunk_y: int, now: float | None = None) -> bool:
        """Return True when the chunk was observed and is still fresh."""
        record = self.get(chunk_x, chunk_y)
        if record is None:
            return False
        moment = time.monotonic() if now is None else now
        return record.status(moment, self.max_age_seconds) == "fresh"

    def needs_refresh(
        self, chunk_x: int, chunk_y: int, now: float | None = None
    ) -> bool:
        """Return True when the chunk is absent, stale or partial."""
        record = self.get(chunk_x, chunk_y)
        if record is None:
            return True
        moment = time.monotonic() if now is None else now
        return record.status(moment, self.max_age_seconds) != "fresh"

    def merge(
        self,
        chunks: Iterable[ChunkRecord],
        now: float | None = None,
    ) -> dict[str, Any]:
        """Merge several chunks into one continuous map description."""
        from dashboard_chunk_map import merge_chunks

        return merge_chunks(self, chunks, now=now)

    # -- reporting ---------------------------------------------------------

    def stats(self, now: float | None = None) -> dict[str, Any]:
        """Return bounded cache statistics for the dashboard status line."""
        from dashboard_chunk_map import cache_stats

        return cache_stats(self, now=now)
