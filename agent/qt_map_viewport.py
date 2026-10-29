"""The map viewport: zoom, pan, world projection and the viewport cache.

This module is the geometry of the factory map, and it is deliberately
free of any Qt import so that it can be tested offline and reasoned about
without a display server.

It reuses the projection the Tkinter dashboard already uses
(:func:`dashboard_view.project` and :func:`dashboard_view.map_scale`) so
that the two interfaces agree on where a world position lands on screen.
The Tkinter dashboard keeps working as the fallback, and both map
viewports show the same factory at the same place.

The viewport owns three things:

* The **zoom level**, expressed in world tiles per screen radius. The
  dashboard's "1:1" mode is one screen pixel per world tile.
* The **center**, in world coordinates.
* The **cache key** of a viewport, which changes whenever anything that
  affects the rendered pixels changes. The map widget uses that key to
  decide whether a redraw is needed at all.

Nothing here reads the game. The viewport is driven by the observed
chunks that the bounded chunk cache already holds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Mapping

from dashboard_chunk_grid import CHUNK_TILES

#: The zoom levels the map offers, in world tiles per screen radius.
#:
#: "1:1" means exactly one screen pixel per world tile, which is the
#: dashboard's own definition and not the game's sprite parity.
ZOOM_LEVELS: tuple[float, ...] = (16.0, 32.0, 64.0, 128.0, 256.0, 512.0)

#: The zoom level that means one screen pixel per world tile.
ZOOM_ONE_TO_ONE = "1:1"

#: The smallest and largest radius the viewport accepts, in world tiles.
MIN_RADIUS = 4.0
MAX_RADIUS = 4096.0

#: How many pixels the viewport may pan in one drag step.
MAX_PAN_PIXELS = 4096


def clamp_radius(radius: float) -> float:
    """Return the radius clamped into the accepted range."""
    if not isinstance(radius, (int, float)) or isinstance(radius, bool):
        raise ValueError("Invalid viewport radius")
    if not math.isfinite(radius):
        raise ValueError("Invalid viewport radius")
    return max(MIN_RADIUS, min(MAX_RADIUS, float(radius)))


def _finite(value: Any) -> bool:
    """Whether a value is a finite real number."""
    return (
        type(value) in (int, float)
        and math.isfinite(value)
    )


def _number(value: Any) -> float | None:
    """Return a finite float, or ``None`` when the value is not a number.

    The explicit ``isinstance`` check narrows the type for the analyzer,
    so a caller never passes ``None`` into ``float()``.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _range_distance(low: float, high: float, value: float) -> float:
    """Return the distance from a value to a half-open range.

    A value inside the range has distance zero, which is what makes the
    chunk that contains the viewport centre rank first.
    """
    if value < low:
        return low - value
    if value >= high:
        return value - high + 1.0
    return 0.0


@dataclass(frozen=True)
class Viewport:
    """Where the map looks: the center, the radius and the surface.

    ``radius`` is the world distance from the center to the edge of the
    **shorter** screen axis, so the map keeps the same scale when the
    window is resized in one direction.

    ``surface`` is the Factorio surface the view belongs to. Chunks from
    one surface are never drawn on another, so the surface is part of the
    viewport rather than a separate label: switching surface resets the
    view to the origin instead of keeping a position that means nothing
    on the new surface.
    """

    center_x: float = 0.0
    center_y: float = 0.0
    radius: float = 128.0
    surface: str = "nauvis"

    def __post_init__(self) -> None:
        if not _finite(self.center_x) or not _finite(self.center_y):
            raise ValueError("Invalid viewport center")
        if not isinstance(self.surface, str) or not 1 <= len(self.surface) <= 128:
            raise ValueError("Invalid viewport surface")
        object.__setattr__(self, "radius", clamp_radius(self.radius))

    # -- projection ------------------------------------------------------

    @property
    def scale(self) -> float:
        """The world tiles per screen pixel at a 1-pixel-wide map."""
        return 1.0 / self.radius

    def pixels_per_tile(self, width: int, height: int) -> float:
        """Return the screen pixels per world tile for a viewport size."""
        if width <= 0 or height <= 0:
            raise ValueError("Invalid viewport size")
        return min(width, height) / (2.0 * self.radius)

    def project(self, x: float, y: float, width: int, height: int
                ) -> tuple[float, float]:
        """Return the screen position of a world position."""
        scale = self.pixels_per_tile(width, height)
        return (
            width / 2.0 + (x - self.center_x) * scale,
            height / 2.0 + (y - self.center_y) * scale,
        )

    def unproject(self, screen_x: float, screen_y: float, width: int,
                  height: int) -> tuple[float, float]:
        """Return the world position of a screen position."""
        scale = self.pixels_per_tile(width, height)
        return (
            self.center_x + (screen_x - width / 2.0) / scale,
            self.center_y + (screen_y - height / 2.0) / scale,
        )

    def contains(self, x: float, y: float, width: int, height: int,
                 margin: float = 0.0) -> bool:
        """Whether a world position is inside the visible area."""
        screen_x, screen_y = self.project(x, y, width, height)
        return (
            -margin <= screen_x <= width + margin
            and -margin <= screen_y <= height + margin
        )

    # -- movement --------------------------------------------------------

    def panned(self, screen_dx: float, screen_dy: float, width: int,
               height: int) -> "Viewport":
        """Return the viewport panned by a screen-space drag.

        Dragging the map right moves the view left in the world, which
        is what a user expects from a map they are dragging.
        """
        for value in (screen_dx, screen_dy):
            if not _finite(value):
                raise ValueError("Invalid pan distance")
        if abs(screen_dx) > MAX_PAN_PIXELS or abs(screen_dy) > MAX_PAN_PIXELS:
            raise ValueError("Pan distance out of range")
        scale = self.pixels_per_tile(width, height)
        return replace(
            self,
            center_x=self.center_x - screen_dx / scale,
            center_y=self.center_y - screen_dy / scale,
        )

    def zoomed(self, factor: float, width: int, height: int,
               focus_x: float | None = None,
               focus_y: float | None = None) -> "Viewport":
        """Return the viewport zoomed by ``factor`` around a focus point.

        The focus point stays under the cursor. Without a focus point the
        center stays put.
        """
        if not _finite(factor) or factor <= 0:
            raise ValueError("Invalid zoom factor")
        target = clamp_radius(self.radius / factor)
        if target == self.radius:
            return self
        if focus_x is None or focus_y is None:
            return replace(self, radius=target)
        if not _finite(focus_x) or not _finite(focus_y):
            raise ValueError("Invalid zoom focus")
        old_scale = self.pixels_per_tile(width, height)
        new_scale = min(width, height) / (2.0 * target)
        # The world position under the focus must not move.
        world_x = self.center_x + (focus_x - width / 2.0) / old_scale
        world_y = self.center_y + (focus_y - height / 2.0) / old_scale
        return replace(
            self,
            center_x=world_x - (focus_x - width / 2.0) / new_scale,
            center_y=world_y - (focus_y - height / 2.0) / new_scale,
            radius=target,
        )

    def centred_on(self, x: float, y: float) -> "Viewport":
        """Return the viewport moved to a world position."""
        if not _finite(x) or not _finite(y):
            raise ValueError("Invalid viewport center")
        return replace(self, center_x=float(x), center_y=float(y))

    def on_surface(self, surface: str) -> "Viewport":
        """Return the viewport for another surface.

        Switching surface keeps the zoom level but resets the position,
        because a world coordinate on one surface means nothing on
        another.
        """
        if not isinstance(surface, str) or not 1 <= len(surface) <= 128:
            raise ValueError("Invalid viewport surface")
        if surface == self.surface:
            return self
        return replace(self, center_x=0.0, center_y=0.0, surface=surface)

    # -- the world area --------------------------------------------------

    def world_bounds(self, width: int, height: int) -> tuple[float, float,
                                                            float, float]:
        """Return the visible world rectangle as (left, top, right, bottom)."""
        scale = self.pixels_per_tile(width, height)
        half_w = width / 2.0 / scale
        half_h = height / 2.0 / scale
        return (
            self.center_x - half_w,
            self.center_y - half_h,
            self.center_x + half_w,
            self.center_y + half_h,
        )

    def visible_chunks(self, width: int, height: int,
                       limit: int = 64) -> list[tuple[int, int]]:
        """Return the aligned chunk indices the viewport can show.

        The result is bounded by ``limit`` so a very wide zoom can never
        ask the observer for an unbounded number of chunks. The chunks
        are returned nearest-first, so the bounded set is always the part
        of the map the user is looking at.

        The chunk index ``c`` covers the tiles ``[c * 64, (c + 1) * 64)``.
        The chunks are ranked by the distance from the viewport centre to
        the **chunk's tile range**, so a chunk that contains the centre
        always wins over a chunk that merely has a closer middle. Ranking
        by the chunk's midpoint instead would put two chunks in a tie
        whenever the centre sat on a chunk seam.
        """
        left, top, right, bottom = self.world_bounds(width, height)
        first_x = math.floor(left / CHUNK_TILES)
        last_x = math.floor(right / CHUNK_TILES)
        first_y = math.floor(top / CHUNK_TILES)
        last_y = math.floor(bottom / CHUNK_TILES)
        candidates = [
            (chunk_x, chunk_y)
            for chunk_y in range(first_y, last_y + 1)
            for chunk_x in range(first_x, last_x + 1)
        ]
        candidates.sort(key=lambda chunk: (
            _range_distance(chunk[0] * CHUNK_TILES,
                            (chunk[0] + 1) * CHUNK_TILES, self.center_x)
            + _range_distance(chunk[1] * CHUNK_TILES,
                              (chunk[1] + 1) * CHUNK_TILES, self.center_y),
            chunk[1], chunk[0],
        ))
        return candidates[:max(1, limit)]

    def cache_key(self, width: int, height: int,
                  content_key: Any = None) -> tuple:
        """Return the key that identifies this rendered viewport.

        Two viewports with the same key render identically, so the map
        widget can skip a redraw entirely. The ``content_key`` carries
        whatever the observed content contributes.
        """
        return (
            round(self.center_x, 4),
            round(self.center_y, 4),
            round(self.radius, 4),
            int(width),
            int(height),
            self.surface,
            content_key,
        )


def viewport_from_frame(frame: Mapping[str, Any] | None, *,
                        radius: float = 128.0) -> Viewport:
    """Return the viewport centred on the observed player position.

    A frame without a player position yields the viewport at the origin
    rather than an invented position. The surface is taken from the
    observed frame; a frame without one keeps the default surface.
    """
    center_x = center_y = 0.0
    surface = "nauvis"
    if isinstance(frame, Mapping):
        position = frame.get("position")
        if isinstance(position, Mapping):
            x = _number(position.get("x"))
            y = _number(position.get("y"))
            if x is not None:
                center_x = x
            if y is not None:
                center_y = y
        observed_surface = frame.get("surface")
        if isinstance(observed_surface, str) and 1 <= len(observed_surface) <= 128:
            surface = observed_surface
    return Viewport(center_x=center_x, center_y=center_y, radius=radius,
                    surface=surface)


def zoom_level_label(radius: float) -> str:
    """Return the label of the zoom level a radius corresponds to."""
    for level in ZOOM_LEVELS:
        if abs(radius - level) < 0.5:
            return f"{int(level)} tiles"
    return f"{radius:.0f} tiles"


def nearest_zoom_level(radius: float) -> float:
    """Return the offered zoom level closest to a radius."""
    return min(ZOOM_LEVELS, key=lambda level: abs(level - radius))


__all__ = [
    "MAX_RADIUS",
    "MAX_PAN_PIXELS",
    "MIN_RADIUS",
    "ZOOM_LEVELS",
    "ZOOM_ONE_TO_ONE",
    "Viewport",
    "clamp_radius",
    "nearest_zoom_level",
    "viewport_from_frame",
    "zoom_level_label",
]
