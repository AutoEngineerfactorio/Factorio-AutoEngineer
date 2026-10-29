"""The map scene: what the factory map draws, prepared once per frame.

This module turns the observed map into a flat, ordered list of drawing
primitives. It is deliberately free of any Qt import, so the scene can be
built and asserted offline, and so the **expensive** part of a redraw
happens once rather than on every paint event.

The scene reuses the verified map layers that the Tkinter dashboard
already uses. Nothing here re-implements the cartography:

* :mod:`dashboard_map_layers` provides the resource patches and the fog
  shading.
* :mod:`dashboard_nature_layers` provides the tree, rock and cliff
  shapes.
* :mod:`dashboard_view` provides the entity footprints and the enemy
  marker colour.

The scene's job is to decide **what is visible** and in **what order**,
and to carry the colours. The Qt painter then draws the primitives.

Truthfulness rules enforced here:

* Only entities the observer actually reported become primitives.
* An entity without observed geometry becomes a **symbol**, never an
  invented rectangle.
* A natural object without an authoritative chart colour is not painted.
* An overlay that the observer did not report is not drawn.
* The scene is bounded: a pathological observation cannot produce an
  unbounded number of primitives.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from dashboard_map_layers import (
    resource_patch_rectangles_by_observed_chunk,
    shade_fog_color,
)
from dashboard_nature_layers import (
    cliff_shape,
    nature_shapes,
    rock_shape,
    tree_canopy_tiles,
    tree_shape,
)
from dashboard_view import enemy_marker_color, entity_screen_bounds
from qt_theme import Palette

#: The drawing layers, in back-to-front order.
LAYERS = (
    "terrain",
    "resource",
    "nature",
    "overlay",
    "building",
    "enemy",
    "player",
)

#: The layers a user may switch off.
TOGGLEABLE_LAYERS = ("resource", "nature", "overlay", "building", "enemy")

#: The upper bound on the primitives one scene may hold.
MAX_PRIMITIVES = 60000

#: The upper bound on the entities one scene may consider.
MAX_ENTITIES = 20000

#: The overlay keys the observer may report.
OVERLAY_KEYS = ("pollution", "electric", "logistics", "turrets")

#: The entity kinds the observer may report.
ENTITY_KINDS = ("resource", "nature", "building", "enemy")


def _number(value: Any) -> float | None:
    """Return a finite float, or ``None`` when the value is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


@dataclass(frozen=True)
class Primitive:
    """One drawable thing on the map.

    ``kind`` is one of :data:`LAYERS`. The geometry fields depend on it,
    and every primitive carries the colour it draws in.
    """

    kind: str
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    color: str = ""
    outline: str = ""
    label: str = ""
    radius: float = 0.0
    data: tuple = ()

    @property
    def is_symbol(self) -> bool:
        """Whether this primitive is a marker rather than a footprint."""
        return self.width <= 0.0 or self.height <= 0.0


@dataclass
class MapScene:
    """The ordered primitives of one map frame."""

    primitives: list[Primitive] = field(default_factory=list)
    layers: dict[str, bool] = field(default_factory=dict)
    #: The world rectangle the scene covers.
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    #: The observed player position, when there was one.
    player: tuple[float, float] | None = None
    #: Whether the observation was partial.
    partial: bool = False
    #: The number of observed entities that were not drawn.
    skipped: int = 0
    #: A short description of what the scene contains.
    note: str = ""

    def __post_init__(self) -> None:
        if not self.layers:
            self.layers = {name: True for name in LAYERS}

    def by_layer(self, kind: str) -> list[Primitive]:
        """Return the primitives of one layer."""
        return [item for item in self.primitives if item.kind == kind]

    def visible_primitives(self) -> list[Primitive]:
        """Return the primitives of the layers that are switched on."""
        return [item for item in self.primitives
                if self.layers.get(item.kind, True)]

    def fingerprint(self) -> tuple:
        """Return a cheap key that identifies this scene's content.

        The map widget uses it to decide whether a repaint is needed at
        all, which is what keeps a redraw from doing the expensive work
        twice.
        """
        return (
            len(self.primitives),
            self.partial,
            self.player,
            tuple(
                (item.kind, round(item.x, 2), round(item.y, 2), item.color)
                for item in self.primitives
            ),
        )


def default_layers() -> dict[str, bool]:
    """Return the layers switched on by default."""
    return {name: True for name in LAYERS}


def terrain_primitives(terrain: Mapping[str, Any] | None) -> list[Primitive]:
    """Return the terrain tiles of an observation.

    The terrain raster is drawn by Qt as an image, so the tiles here are
    only the individually reported tiles that the raster does not carry.
    A charted-but-not-visible tile is shaded by the same factor the
    backend uses, so both paths agree on how Factorio darkens fogged
    terrain.
    """
    if not isinstance(terrain, Mapping):
        return []
    primitives: list[Primitive] = []
    for tile in terrain.get("tiles") or []:
        if not isinstance(tile, Mapping):
            continue
        x = _number(tile.get("x"))
        y = _number(tile.get("y"))
        if x is None or y is None:
            continue
        color = tile.get("color")
        if not isinstance(color, str) or not color:
            continue
        if tile.get("visible") is False:
            color = shade_fog_color(color) or color
        primitives.append(Primitive(
            kind="terrain", x=x, y=y, width=1.0, height=1.0, color=color))
        if len(primitives) >= MAX_PRIMITIVES:
            break
    return primitives


def resource_primitives(entities: Iterable[Mapping[str, Any]],
                        observed_chunks: Iterable[Mapping[str, Any]] | None,
                        chunk_tiles: int) -> list[Primitive]:
    """Return the filled resource patches of the observed entities.

    The patches come from the verified map layer, so an ore field reads
    as one continuous patch like the in-game map rather than as a set of
    outlined individual deposits.
    """
    entities = list(entities or [])
    chunks = list(observed_chunks or [])
    if not entities or not chunks:
        return []
    rectangles = resource_patch_rectangles_by_observed_chunk(
        entities, chunks, chunk_tiles)
    from dashboard_map_layers import resource_patch_color

    primitives: list[Primitive] = []
    for name, boxes in rectangles.items():
        color = resource_patch_color(name)
        for left, top, right, bottom in boxes:
            primitives.append(Primitive(
                kind="resource",
                x=float(left), y=float(top),
                width=float(right - left + 1),
                height=float(bottom - top + 1),
                color=color,
                label=name,
            ))
            if len(primitives) >= MAX_PRIMITIVES:
                return primitives
    return primitives


def nature_primitives(entities: Iterable[Mapping[str, Any]]
                      ) -> list[Primitive]:
    """Return the natural objects of the observed entities.

    A tree, a rock and a cliff keep their own shape and their own
    authoritative chart colour. An object without a chart colour is not
    painted at all, because the runtime's white is the game's "no chart
    colour" marker and not a colour.
    """
    primitives: list[Primitive] = []
    for shape in nature_shapes(list(entities or [])):
        color = shape.color
        if not isinstance(color, str) or not color or color == "#ffffff":
            continue
        kind = shape.kind
        if kind == "tree":
            radius = tree_canopy_tiles(shape)
        elif kind == "cliff":
            radius = cliff_shape(shape)
        elif kind == "rock":
            radius = rock_shape(shape)
        else:
            radius = tree_shape(shape)
        primitives.append(Primitive(
            kind="nature", x=shape.x, y=shape.y,
            radius=float(radius), color=color,
            label=shape.name,
            data=(kind,),
        ))
        if len(primitives) >= MAX_PRIMITIVES:
            break
    return primitives


def entity_primitives(entities: Iterable[Mapping[str, Any]],
                      pixels_per_tile: float) -> list[Primitive]:
    """Return the buildings and the enemies of the observed entities.

    A building is drawn with its observed footprint when it has one, and
    as a symbol when it does not. An enemy is always a symbol, because
    the observer reports only the entities it can currently see.
    """
    primitives: list[Primitive] = []
    for entity in entities or []:
        if not isinstance(entity, Mapping):
            continue
        kind = entity.get("kind")
        if kind not in ("building", "enemy"):
            continue
        x = _number(entity.get("x"))
        y = _number(entity.get("y"))
        if x is None or y is None:
            continue
        name = entity.get("name")
        if kind == "enemy":
            primitives.append(Primitive(
                kind="enemy", x=x, y=y, radius=5.0,
                color=enemy_marker_color(dict(entity)),
                outline="#ffd9d0",
                label=name if isinstance(name, str) else "",
            ))
        else:
            bounds = entity_screen_bounds(dict(entity), 0.0, 0.0,
                                          pixels_per_tile)
            if bounds is None:
                primitives.append(Primitive(
                    kind="building", x=x, y=y, radius=3.0,
                    color=Palette.BUILDING, label=name if isinstance(name, str) else "",
                ))
            else:
                left, top, right, bottom = bounds
                primitives.append(Primitive(
                    kind="building",
                    x=x + left, y=y + top,
                    width=right - left, height=bottom - top,
                    color=Palette.BUILDING,
                    outline="#111416",
                    label=name if isinstance(name, str) else "",
                ))
        if len(primitives) >= MAX_PRIMITIVES:
            break
    return primitives


def overlay_primitives(overlays: Mapping[str, Any] | None
                        ) -> list[Primitive]:
    """Return the observed overlay markers.

    Only an overlay the observer actually reported is drawn. The
    pollution, electric, logistics and turret overlays keep their own
    colours so the map reads like the in-game map.
    """
    if not isinstance(overlays, Mapping):
        return []
    available = overlays.get("available")
    if not isinstance(available, Mapping):
        available = {}
    primitives: list[Primitive] = []
    for key in OVERLAY_KEYS:
        if available.get(key) is not True:
            continue
        entries = overlays.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            x = _number(entry.get("x"))
            y = _number(entry.get("y"))
            if x is None or y is None:
                continue
            if key == "pollution":
                value = _number(entry.get("value")) or 0.0
                if value <= 0:
                    continue
                red = min(220, 80 + int(25 * math.log1p(value)))
                primitives.append(Primitive(
                    kind="overlay", x=x, y=y,
                    width=float(_number(entry.get("width")) or 1.0),
                    height=float(_number(entry.get("height")) or 1.0),
                    color=f"#{red:02x}3020", data=("pollution",),
                ))
            elif key == "electric":
                primitives.append(Primitive(
                    kind="overlay", x=x, y=y,
                    radius=float(_number(entry.get("radius")) or 1.0),
                    color="#447799", outline="#78b8ed", data=("electric",),
                ))
            elif key == "logistics":
                primitives.append(Primitive(
                    kind="overlay", x=x, y=y,
                    radius=float(_number(entry.get("construction")) or 0.0),
                    color="#68b568", outline="#db9b42", data=("logistics",),
                ))
            elif key == "turrets":
                primitives.append(Primitive(
                    kind="overlay", x=x, y=y,
                    radius=float(_number(entry.get("radius")) or 1.0),
                    color="#00000000", outline="#df6672", data=("turrets",),
                ))
            if len(primitives) >= MAX_PRIMITIVES:
                return primitives
    return primitives


def build_scene(merged_map: Mapping[str, Any] | None, *,
                player: Mapping[str, Any] | None = None,
                pixels_per_tile: float = 1.0,
                layers: Mapping[str, bool] | None = None,
                chunk_tiles: int = 64) -> MapScene:
    """Build the scene of one observed map.

    ``merged_map`` is the merged map the chunk cache produces. Nothing
    is invented: an empty or missing map produces an empty scene, not a
    fabricated factory.
    """
    scene = MapScene(layers=dict(layers) if layers else default_layers())
    if not isinstance(merged_map, Mapping):
        scene.note = "No observed map"
        return scene

    entities = merged_map.get("entities") or []
    if len(entities) > MAX_ENTITIES:
        scene.skipped = len(entities) - MAX_ENTITIES
        entities = entities[:MAX_ENTITIES]
    scene.partial = bool(merged_map.get("partial"))

    terrain = merged_map.get("terrain", merged_map)
    if not isinstance(terrain, Mapping):
        terrain = {}
    scene.primitives.extend(terrain_primitives(terrain))

    observed_chunks = [
        {"x": chunk[0], "y": chunk[1]}
        for chunk in (merged_map.get("origins") or [])
        if isinstance(chunk, (list, tuple)) and len(chunk) == 2
    ]
    scene.primitives.extend(
        resource_primitives(entities, observed_chunks, chunk_tiles))
    scene.primitives.extend(nature_primitives(entities))
    scene.primitives.extend(
        overlay_primitives(merged_map.get("overlays")))
    scene.primitives.extend(entity_primitives(entities, pixels_per_tile))

    if isinstance(player, Mapping):
        px = _number(player.get("x"))
        py = _number(player.get("y"))
        if px is not None and py is not None:
            scene.player = (px, py)
            scene.primitives.append(Primitive(
                kind="player", x=px, y=py, radius=7.0,
                color=Palette.PLAYER, outline="#101d20",
            ))

    scene.primitives = scene.primitives[:MAX_PRIMITIVES]
    scene.note = f"{len(scene.primitives)} primitives"
    return scene


__all__ = [
    "ENTITY_KINDS",
    "LAYERS",
    "MAX_ENTITIES",
    "MAX_PRIMITIVES",
    "OVERLAY_KEYS",
    "TOGGLEABLE_LAYERS",
    "MapScene",
    "Primitive",
    "build_scene",
    "default_layers",
    "entity_primitives",
    "nature_primitives",
    "overlay_primitives",
    "resource_primitives",
    "terrain_primitives",
]
