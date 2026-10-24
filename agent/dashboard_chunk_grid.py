"""Aligned map-chunk grid for the read-only AutoEngineer dashboard.

The dashboard observes the world in aligned 64x64 tiles chunks. This module
owns the geometry of that grid and the validation of chunk requests, so the
backend, the observer and the cache all agree on exactly one grid.

Rules:

* The grid is a floor division, so negative world coordinates floor towards
  negative infinity and never truncate towards zero.
* A chunk request is only valid as a pair of bounded integers. Booleans,
  floats, strings and out-of-range values are rejected before they can reach
  the backend or the cache.
* The chunk index is a grid coordinate, not a world coordinate. The world
  origin of a chunk is always ``index * 64``.
"""
from __future__ import annotations

import math
from typing import Any

CHUNK_TILES = 64
"""Size of one observed map chunk in tiles, matching the backend grid."""

MAX_CHUNK_COORD = 100000
"""Absolute bound on a chunk index, matching the backend's own bound."""

ENTITY_KINDS = ("resource", "nature", "building", "enemy")
"""The observed entity layers the dashboard map understands."""


def chunk_of(x: float, y: float) -> tuple[int, int]:
    """Return the aligned chunk index containing a world position."""
    return (
        math.floor(x / CHUNK_TILES),
        math.floor(y / CHUNK_TILES),
    )


def chunk_origin(chunk_x: int, chunk_y: int) -> dict[str, float]:
    """Return the world origin (top-left tile) of an aligned chunk."""
    return {"x": chunk_x * CHUNK_TILES, "y": chunk_y * CHUNK_TILES}


def chunk_key(surface: str, chunk_x: int, chunk_y: int) -> tuple[str, int, int]:
    """Return the cache key for a surface-scoped chunk."""
    return (surface, chunk_x, chunk_y)


def validate_chunk_request(value: Any) -> tuple[int, int]:
    """Validate a requested chunk index pair.

    Rejects booleans, floats, strings, out-of-range values and non-integers
    so a malformed request cannot reach the backend or the cache.
    """
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("Chunk request must be a pair")
    chunk_x, chunk_y = value
    for number in (chunk_x, chunk_y):
        if type(number) is not int:
            raise ValueError("Chunk coordinates must be integers")
        if not -MAX_CHUNK_COORD <= number <= MAX_CHUNK_COORD:
            raise ValueError("Chunk coordinates out of range")
    return (chunk_x, chunk_y)


def chunks_for_viewport(
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
    limit: int = 64,
) -> list[tuple[int, int]]:
    """Return the chunk indices a viewport touches, nearest first.

    The result is bounded by ``limit``. The chunks are ordered by their
    distance from the viewport centre so the closest, most relevant chunks
    are requested first and a large viewport never turns into one unbounded
    sweep of the world.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("Chunk limit must be a positive integer")
    if not all(math.isfinite(value) for value in (center_x, center_y, radius_x, radius_y)):
        raise ValueError("Invalid viewport bounds")
    radius_x = max(0.0, abs(radius_x))
    radius_y = max(0.0, abs(radius_y))
    min_x, max_x = chunk_of(center_x - radius_x, center_y - radius_y)[0], chunk_of(
        center_x + radius_x, center_y + radius_y
    )[0]
    min_y, max_y = chunk_of(center_x - radius_x, center_y - radius_y)[1], chunk_of(
        center_x + radius_x, center_y + radius_y
    )[1]
    candidates = [
        (chunk_x, chunk_y)
        for chunk_x in range(min_x, max_x + 1)
        for chunk_y in range(min_y, max_y + 1)
    ]
    center_chunk = chunk_of(center_x, center_y)
    candidates.sort(
        key=lambda item: (
            (item[0] - center_chunk[0]) ** 2 + (item[1] - center_chunk[1]) ** 2,
            item[1],
            item[0],
        )
    )
    return candidates[:limit]
