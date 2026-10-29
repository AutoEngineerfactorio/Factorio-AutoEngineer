"""Resource-patch map layer and the fog-of-war state model.

The Factorio in-game map renders an ore field as one continuous coloured
patch. Drawing every observed deposit as its own outlined shape instead
produces the black-outlined checkerboard look this module replaces.

This module is deliberately free of any GUI dependency: it converts the
*observed* resource entities into a tile grid that the view can paint as
filled overlays. It never invents terrain, resources or positions.

Truthfulness rules enforced here:

* Only entities the observer actually reported are rasterized.
* An entity without observed geometry contributes only its own occupied
  tile; no width/height/bounds is inferred from the entity name.
* The patch grid is a superset of the observed deposits only in the sense
  that each deposit occupies the tiles its own observed footprint covers.
* Unobserved space is never represented here; the terrain layer keeps it
  black.

The fog-of-war state model lives here too, so the backend's raster and the
dashboard's renderer agree on one definition. Factorio 2.1.23 distinguishes
exactly three map states for a tile:

``unexplored``
    The chunk was never charted. The game draws nothing there: the tile is
    black. Nothing about it may be revealed.

``charted``
    The chunk was charted but is not currently visible. The game draws the
    terrain darkened by the map shading factor. Live entities are **not**
    reported for these chunks.

``visible``
    The chunk is charted and currently visible. The game draws the terrain
    at full brightness, and the observer reports the live entities in it.
"""

import math

# Colours taken from the verified Factorio 2.1.23 base prototypes
# (data/base/prototypes/entity/resources.lua, `map_color`). Coal is pure
# black in the game, which would be invisible against the terrain
# underlay, so it keeps the game's hue at a legible lightness.
RESOURCE_PATCH_COLORS = {
    "iron-ore": "#6a8694",
    "copper-ore": "#cd6337",
    "coal": "#31353a",
    "stone": "#b09c6d",
    "uranium-ore": "#00b300",
    "crude-oil": "#c733c4",
}
FALLBACK_RESOURCE_COLOR = "#be92b9"

# A deposit that reports no geometry at all still occupies the tile it
# was observed on. That is the only tile the observer asserted.
DEFAULT_RESOURCE_TILE = 1

# The three fog-of-war states of a map tile, in Factorio's own terms.
FOG_UNEXPLORED = "unexplored"
FOG_CHARTED = "charted"
FOG_VISIBLE = "visible"

FOG_STATES = (FOG_UNEXPLORED, FOG_CHARTED, FOG_VISIBLE)
"""Every map-tile visibility state Factorio 2.1.23 can report."""

# Factorio 2.1.23 shades a charted-but-not-visible map tile by this factor.
# The backend applies it when it builds the terrain palette, so the
# renderer must not apply it a second time.
FOG_SHADING_FACTOR = 0.6667

# The colour Factorio uses for an unexplored tile.
FOG_BLACK = "#000000"


def fog_state(charted, visible):
    """Return the fog state of a tile from the game's own two predicates.

    ``is_chunk_visible`` already implies that the chunk is charted, so a
    visible chunk is visible regardless of the charted flag. A chunk that
    is neither charted nor visible was never explored.
    """
    if visible:
        return FOG_VISIBLE
    if charted:
        return FOG_CHARTED
    return FOG_UNEXPLORED


def shade_fog_color(color, factor=FOG_SHADING_FACTOR):
    """Return ``color`` darkened by Factorio's map shading factor.

    Returns None for a colour that is not a usable ``#rrggbb`` value, so
    an unusable colour is never painted as a guessed shade.
    """
    if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
        return None
    try:
        channels = [int(color[position:position + 2], 16) for position in (1, 3, 5)]
    except ValueError:
        return None
    shaded = [max(0, min(255, int(round(channel * factor)))) for channel in channels]
    return "#%02x%02x%02x" % tuple(shaded)


def resource_patch_color(name):
    """Map-like colour for an observed resource prototype name."""
    return RESOURCE_PATCH_COLORS.get(name, FALLBACK_RESOURCE_COLOR)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _number(container, key):
    """Return a finite number from a mapping, or None if it is not one."""
    if not isinstance(container, dict):
        return None
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def occupied_tiles(entity):
    """Return the world tiles an observed resource entity occupies.

    The tile set comes from the observed bounding box when the observer
    supplied one, from the observed width/height when it supplied those,
    and otherwise from the single observed position. No dimension is ever
    derived from the entity name.
    """
    x, y = entity.get("x"), entity.get("y")
    if not _finite(x) or not _finite(y):
        return []
    if "bounds" in entity:
        box = entity["bounds"]
        if not isinstance(box, dict):
            return []
        left_top, right_bottom = box.get("left_top"), box.get("right_bottom")
        x0 = _number(left_top, "x")
        y0 = _number(left_top, "y")
        x1 = _number(right_bottom, "x")
        y1 = _number(right_bottom, "y")
        if x0 is None or y0 is None or x1 is None or y1 is None:
            return []
        if x1 <= x0 or y1 <= y0:
            return []
        min_x, max_x = math.floor(x0), math.floor(x1 - 1e-9)
        min_y, max_y = math.floor(y0), math.floor(y1 - 1e-9)
    elif "width" in entity and "height" in entity:
        width, height = entity["width"], entity["height"]
        if not _finite(width) or not _finite(height) or width <= 0 or height <= 0:
            return []
        min_x, max_x = math.floor(x - width / 2), math.floor(x + width / 2 - 1e-9)
        min_y, max_y = math.floor(y - height / 2), math.floor(y + height / 2 - 1e-9)
    else:
        min_x = max_x = math.floor(x)
        min_y = max_y = math.floor(y)
    tiles = []
    for ty in range(min_y, max_y + 1):
        for tx in range(min_x, max_x + 1):
            tiles.append((tx, ty))
    return tiles


def resource_patch_cells(entities, origin=None):
    """Rasterize observed resource entities into a resource -> tile set map.

    Adjacent deposits of the same resource merge into one continuous patch
    because the result is a set of tiles, not a list of shapes. Deposits of
    different resources keep separate patches.

    `origin` optionally restricts the result to the charted observation
    window; tiles outside it are dropped rather than drawn.
    """
    patches: dict[str, set[tuple[int, int]]] = {}
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("kind") != "resource":
            continue
        name = entity.get("name")
        if not isinstance(name, str) or not name:
            continue
        cells = patches.setdefault(name, set())
        for tile in occupied_tiles(entity):
            if origin is not None:
                if not (
                    origin["x"] <= tile[0] < origin["x"] + origin["width"]
                    and origin["y"] <= tile[1] < origin["y"] + origin["height"]
                ):
                    continue
            cells.add(tile)
    return patches


def fill_observed_field(tiles, origin=None):
    """Close the gaps inside one observed resource field.

    A LIVE READ-ONLY observation of the running Factorio 2.1.23 game shows
    that an ore field is reported as many individual ore nodes: 436
    ``copper-ore`` nodes spread over a 24x25 tile area, 636 ``iron-ore``
    nodes over 31x34 tiles. Each node's own observed bounding box is only
    0.195 tiles across, so a node covers a fraction of one tile and the
    field reads as scattered dots instead of one patch.

    This function closes that gap the way the game's own map does, without
    inventing a deposit that was not observed:

    * A tile that contains at least one observed node is always kept.
    * An empty tile is added only when it is enclosed by observed nodes on
      at least three of its four sides. A tile on the edge of the field
      therefore keeps its true, observed boundary.
    * Two deposits that are separated by more than one tile of empty space
      stay separate, because the fill cannot bridge a gap of two or more
      tiles.

    The result is the observed field's own footprint, not a smooth blob:
    every added tile is surrounded by observed ore on three sides.
    """
    if not tiles:
        return set()
    observed = set(tiles)
    filled = set(observed)
    candidates: set[tuple[int, int]] = set()
    for x, y in observed:
        candidates.update(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    for x, y in candidates - observed:
        if origin is not None and not (
            origin["x"] <= x < origin["x"] + origin["width"]
            and origin["y"] <= y < origin["y"] + origin["height"]
        ):
            continue
        neighbours = sum(
            ((x + dx, y + dy) in observed)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        if neighbours >= 3:
            filled.add((x, y))
    return filled


def resource_patch_groups(tiles):
    """Split one resource's tiles into its separate observed deposits.

    Two tiles belong to the same deposit when they are within one tile of
    each other, which is how the observed ore nodes of one field cluster.
    Two fields that are separated by empty space stay separate patches, so
    the map never merges two distinct deposits into one shape.
    """
    if not tiles:
        return []
    remaining = set(tiles)
    groups: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        group = {seed}
        frontier = [seed]
        while frontier:
            x, y = frontier.pop()
            for neighbour in (
                (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1),
                (x + 1, y + 1), (x + 1, y - 1), (x - 1, y + 1), (x - 1, y - 1),
            ):
                if neighbour in remaining:
                    remaining.discard(neighbour)
                    group.add(neighbour)
                    frontier.append(neighbour)
        groups.append(group)
    return groups


def merged_patch_rectangles(tiles):
    """Merge a tile set into the fewest axis-aligned rectangles.

    Rectangles are merged greedily along the x axis for each row, then rows
    with identical spans are merged vertically. The result is a filled patch
    shape with no per-deposit outline, which is what the in-game map shows.
    """
    if not tiles:
        return []
    rows: dict[int, list[tuple[int, int]]] = {}
    for tx, ty in tiles:
        rows.setdefault(ty, []).append((tx, tx))
    spans: dict[int, list[tuple[int, int]]] = {}
    for ty, intervals in rows.items():
        intervals.sort()
        merged: list[tuple[int, int]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        spans[ty] = merged
    rectangles = []
    for ty in sorted(spans):
        for start, end in spans[ty]:
            rectangles.append([start, ty, end, ty])
    # Merge vertically stacked rectangles that share the same x span.
    by_span: dict[tuple[int, int], list[list[int]]] = {}
    for rect in rectangles:
        by_span.setdefault((rect[0], rect[2]), []).append(rect)
    result = []
    for (x0, x1), group in by_span.items():
        group.sort(key=lambda r: r[1])
        current = list(group[0])
        for rect in group[1:]:
            if rect[1] == current[3] + 1:
                current[3] = rect[3]
            else:
                result.append(current)
                current = list(rect)
        result.append(current)
    result.sort(key=lambda r: (r[1], r[0]))
    return [tuple(r) for r in result]


def observed_chunk_tile_set(observed_chunks, chunk_tiles):
    """Return the set of world tiles covered by the observed chunks.

    The observer reports one aligned chunk grid, so a chunk is named by its
    chunk index and covers ``chunk_tiles`` world tiles in each direction.
    The returned set is the union of those tiles, which is the exact region
    the dashboard is allowed to paint: a tile outside it belongs to a chunk
    that was never observed and must stay unexplored.
    """
    tiles: set[tuple[int, int]] = set()
    for chunk in observed_chunks or []:
        if not isinstance(chunk, dict):
            continue
        chunk_x = chunk.get("x")
        chunk_y = chunk.get("y")
        if not isinstance(chunk_x, int) or not isinstance(chunk_y, int):
            continue
        base_x = chunk_x * chunk_tiles
        base_y = chunk_y * chunk_tiles
        for ty in range(base_y, base_y + chunk_tiles):
            for tx in range(base_x, base_x + chunk_tiles):
                tiles.add((tx, ty))
    return tiles


def resource_patch_rectangles_by_observed_chunk(
    entities, observed_chunks, chunk_tiles
):
    """Return filled patch rectangles for the observed chunks only.

    A resource entity belongs to a chunk by its observed **position**, the
    same way the nature layer assigns natural objects to a chunk. Its
    observed footprint may cross a chunk seam, and that is legitimate: the
    observer reported the node's real bounding box.

    The rule this function enforces is therefore:

    * An entity whose position lies in an observed chunk contributes its
      full observed footprint.
    * A tile of that footprint that lies in a *neighbouring observed* chunk
      is kept, because the neighbour was observed and the tile is part of
      the observed node.
    * A tile that lies in a neighbouring *unobserved* chunk is dropped, so
      unexplored space never shows an ore tile.

    Each entity is visited exactly once, through the chunk its position
    falls in, so a seam-crossing node is never painted twice.
    """
    allowed = observed_chunk_tile_set(observed_chunks, chunk_tiles)
    if not allowed:
        return {}
    observed_keys = {
        (chunk["x"], chunk["y"])
        for chunk in observed_chunks or []
        if isinstance(chunk, dict)
        and isinstance(chunk.get("x"), int)
        and isinstance(chunk.get("y"), int)
    }
    patches: dict[str, set[tuple[int, int]]] = {}
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("kind") != "resource":
            continue
        name = entity.get("name")
        if not isinstance(name, str) or not name:
            continue
        x = _number(entity, "x")
        y = _number(entity, "y")
        if x is None or y is None:
            continue
        # Membership is decided by the observed position, not by the tiles
        # the footprint covers, so a seam-crossing node is handled once.
        owner = (math.floor(x / chunk_tiles), math.floor(y / chunk_tiles))
        if owner not in observed_keys:
            continue
        cells = patches.setdefault(name, set())
        for tile in occupied_tiles(entity):
            if tile in allowed:
                cells.add(tile)
    result: dict[str, list[tuple[int, int, int, int]]] = {}
    for name, observed in patches.items():
        rectangles: list[tuple[int, int, int, int]] = []
        for group in resource_patch_groups(observed):
            rectangles.extend(merged_patch_rectangles(fill_observed_field(group)))
        if rectangles:
            result[name] = rectangles
    return result


def resource_patch_rectangles(entities, origin=None):
    """Return filled patch rectangles per observed resource name.

    An ore field is observed as many individual ore nodes, each far smaller
    than one tile, so the nodes are first grouped into the separate
    observed deposits they form and each deposit is then filled in the way
    the game's own map fills it: a tile surrounded by observed ore on three
    sides belongs to the same deposit.

    This is a cartographic approximation of the game's patch fill, never a
    claim that an additional resource entity exists. Two deposits that are
    separated by empty space stay separate patches, and the outer boundary
    of a deposit stays exactly on the observed nodes.
    """
    patches = resource_patch_cells(entities, origin)
    result = {}
    for name, observed in patches.items():
        rectangles: list[tuple[int, int, int, int]] = []
        for group in resource_patch_groups(observed):
            filled = fill_observed_field(group, origin)
            rectangles.extend(merged_patch_rectangles(filled))
        if rectangles:
            result[name] = rectangles
    return result
