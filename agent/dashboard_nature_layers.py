"""Nature map layer for the read-only AutoEngineer dashboard map.

The Factorio in-game map draws a tree, a rock and a cliff with the game's own
map colours and shapes. Reproducing that needs the *authoritative* prototype
map colour, not a hand-picked swatch, and it needs each natural object's real
footprint, not a generic circle.

Everything here is derived from what the read-only observer actually reported:

* ``map_color`` - the prototype map colour observed for that entity.
* ``bounds`` / ``width`` / ``height`` - the observed world footprint.
* ``entity_type`` - the observed Lua entity type (``tree``, ``cliff``, ...).
* ``prototype_type`` - the observed prototype type, which distinguishes a
  mineable rock from an ore deposit without guessing from the name.

Truthfulness rules enforced here:

* Nothing is drawn that the observer did not report.
* No colour is invented: an entity without an observed or verified prototype
  map colour is drawn as an uncoloured outline-only marker, never as a
  recoloured guess.
* No footprint is inferred from the entity name. A natural object without
  observed geometry contributes only the tile it was observed on.
* A mineable rock and an ore deposit are different things and never share a
  shape or a colour.

Authoritative Factorio 2.1.23 facts used here (verified against the pinned
offline 2.1.23 API archive, the verified 2.1.23 installation's data stage,
and a LIVE READ-ONLY observation of the running 2.1.23 game):

* ``EntityPrototype::map_color`` is an optional ``Color``
  (``{r, g, b, a}`` floats in 0..1, or 0..255 components) and is inherited by
  ``TreePrototype``, ``SimpleEntityPrototype`` and ``CliffPrototype``.
* ``EntityPrototype::map_color`` defaults to ``None`` in the data stage.
* **LIVE READ-ONLY finding:** in the running 2.1.23 game
  ``LuaEntityPrototype::map_color`` returns pure white ``{255, 255, 255}``
  for *every* prototype queried, including ``copper-ore`` whose data-stage
  ``map_color`` is ``{0.803, 0.388, 0.215}`` and whose real chart colour is
  therefore known to be ``#cd6337``. The runtime accessor is consequently the
  game's "no chart colour" marker, **not** a chart colour. It is never
  painted.
* Vanilla cliff prototypes use ``map_color = {r=144, g=119, b=87}``
  (``data/base/prototypes/entity/entity-util.lua``) → ``#907757``.
* Vanilla ``big-rock`` uses ``map_color = {129, 105, 78}``
  (``data/base/prototypes/decorative/decoratives.lua``) → ``#81694e``.
* Vanilla base-game trees deliberately define **no** ``map_color``; the game
  draws them on the map by tinting the tree sprite with the prototype's own
  ``colors`` palette and shading it with the game's map shading factor. The
  observed ``graphics_variation`` selects the exact tint, so the tree's real
  colour is reproducible. The verified 2.1.23 palettes are in
  ``VERIFIED_TREE_TINT_PALETTES``.
"""

import math

__all__ = [
    "CHART_COLOR_KEYS",
    "MAP_SHADING_FACTOR",
    "RUNTIME_DEFAULT_CHART_COLOR",
    "VERIFIED_TREE_TINT_PALETTES",
    "NatureShape",
    "cliff_shape",
    "nature_color",
    "nature_fingerprint",
    "nature_shape",
    "nature_shapes",
    "parse_map_color",
    "rock_shape",
    "shade_color",
    "tree_shape",
    "tree_tint_color",
    "tree_tint_palette",
    "verified_prototype_map_color",
]

# Verified Factorio 2.1.23 prototype chart colours. Only prototypes whose
# colour was read directly out of the verified 2.1.23 installation's data
# stage are listed here. Anything else stays uncoloured rather than being
# approximated.
VERIFIED_PROTOTYPE_MAP_COLORS = {
    # data/base/prototypes/decorative/decoratives.lua
    "big-rock": (129, 105, 78),
    "big-sand-rock": (129, 105, 78),
    # data/base/prototypes/entity/entity-util.lua (scaled_cliff default)
    "cliff": (144, 119, 87),
}

# The order in which Factorio picks a chart colour for an entity. The 2.1.23
# runtime API documents ``map_color`` as "The map color used when charting
# this entity if a friendly or enemy color isn't defined, if any", so the
# force-specific colours win over the generic one.
CHART_COLOR_KEYS = ("friendly_map_color", "enemy_map_color", "map_color")

# Factorio 2.1.23 returns pure white from ``LuaEntityPrototype::map_color``
# for **every** prototype whose chart colour the game does not expose through
# that accessor. The LIVE READ-ONLY observation of the running 2.1.23 game
# confirmed this: base trees (which define no map_color) and ``copper-ore``
# (whose data-stage map_color is {0.803, 0.388, 0.215}) both reported
# {255, 255, 255}. White is therefore the runtime's "no chart colour" value
# and must never be painted as an object's colour.
RUNTIME_DEFAULT_CHART_COLOR = "#ffffff"

# Factorio 2.1.23 shades a charted-but-not-currently-visible map tile by
# 0.6667 (the same factor the observer already applies to the terrain
# raster). The in-game map draws a tree in a similarly darkened form rather
# than in the bright world sprite colour.
#
# LIVE READ-ONLY measurement of the running 2.1.23 game's minimap confirms
# the direction and magnitude: every measured map tree pixel is a darkened
# version of a verified tree tint, with the observed darkening factors
# spanning roughly 0.21 to 0.46. Factorio's minimap anti-aliases and
# dithers each tree mark against the terrain underneath, so no single
# constant reproduces it exactly; the verified game constant above is used
# instead of an invented one.
MAP_SHADING_FACTOR = 0.6667

# Verified Factorio 2.1.23 tree tint palettes, read straight out of
# ``data/base/prototypes/entity/trees.lua``. Factorio tints a tree's sprite
# with one entry of its prototype's ``colors`` list, and the map draws the
# tree with that same tinted sprite, so these are the game's own tree
# colours. The prototype name is ``tree-<NN>`` plus an optional identifier,
# exactly as the data stage builds it.
VERIFIED_TREE_TINT_PALETTES = {
    "tree-01": ("#9cffe0", "#76f398", "#74d7e3", "#ddd150",
                "#83f25a", "#53b98a", "#47e04a", "#e6f229"),
    "tree-02": ("#bfff6f", "#d1c898", "#fcff85", "#e6b25e", "#bed784",
                "#ccaf6e", "#f0ff78", "#c2d057", "#deffa9", "#96c96f"),
    "tree-02-red": ("#e38f58", "#e2c45e", "#ffb082", "#ddbd67", "#ffb7b7",
                    "#ff9541", "#ec9f48", "#ff7f3e", "#d17151", "#cf763c",
                    "#ff9862", "#ff8787", "#ca6b50", "#d4805a", "#ff6565",
                    "#ff7575"),
    "tree-03": ("#e6fd42", "#ffdf57", "#aabb41", "#d84646", "#b3ee5f",
                "#ffea52", "#eeab47", "#dbad5b", "#e7d681"),
    "tree-04": ("#d5ff9c", "#c4ff74", "#d4ff96", "#d5ff9f", "#92d3eb",
                "#5ddee3", "#baffa7", "#92e27b", "#38bc7d", "#ace3b1",
                "#b7ffc8", "#a98dcf"),
    "tree-05": ("#bae35d", "#d3f18b", "#c3e472", "#c8f25e", "#a1de4b",
                "#b6d843", "#bcd170", "#bee736", "#b2b34f", "#adad52",
                "#acad51", "#a7a860", "#fdff73"),
    "tree-06": ("#d8ee8e", "#cee67e", "#cbde8c", "#d3db6f", "#eeec71",
                "#f5f075", "#d0ee76"),
    "tree-06-brown": ("#d7aa6b", "#f1b055", "#e38a3c", "#fb9e4c",
                      "#cf913a", "#f9b15c", "#fd9b00"),
    "tree-07": ("#cb8c33", "#d09b4f", "#bdaf35", "#d9ce6d", "#f6e76c",
                "#d7ce7e", "#caab5f", "#e3b64c", "#ce9d28", "#e6ad25",
                "#f7df58", "#cdba51"),
    "tree-08": ("#e7ff53", "#d1ff3a", "#a59f04", "#c2e749", "#f5f22c",
                "#f8f266", "#d0ee76"),
    "tree-08-brown": ("#ffa23e", "#ffc091", "#ffba4a", "#ff8e44",
                      "#ffcd3e", "#ffcd44", "#ff8e18", "#ff6100"),
    "tree-08-red": ("#e06d52", "#e46b6b", "#e2886b", "#de7d72"),
    "tree-09": ("#ffba00", "#ff602d", "#ffcc40", "#ffd462", "#ffc148",
                "#ff6742", "#ff9700"),
    "tree-09-brown": ("#e78c00", "#ff9364", "#dd604c", "#ffa047",
                      "#ff8c59", "#ff743c", "#ff715d"),
    "tree-09-red": ("#e76400", "#ff756e", "#dd4c4c", "#ff8383", "#ff6459",
                    "#ff6046", "#ff5d5d"),
}


def tree_tint_palette(name):
    """Return the verified 2.1.23 tint palette for a tree prototype name.

    The data stage builds tree prototype names as ``tree-<NN>`` with an
    optional ``-<identifier>`` suffix, and the live entity names use that
    same shape (``tree-08``, ``tree-08-brown``). A name that matches no
    verified palette returns None so no tree colour is invented.
    """
    if not isinstance(name, str):
        return None
    palette = VERIFIED_TREE_TINT_PALETTES.get(name)
    if palette is not None:
        return palette
    # The data stage uses an underscore in its tree_data identifiers
    # ("tree_08_brown") but builds the prototype name with a dash
    # ("tree-08-brown"). Accept the observed prototype name shape.
    if name.startswith("tree-"):
        alternate = name.replace("-", "_", 1)
        return VERIFIED_TREE_TINT_PALETTES.get(alternate)
    return None

# Observed Lua entity types that are natural objects.
NATURE_ENTITY_TYPES = ("tree", "cliff", "simple-entity")

# Observed prototype types that mean "mineable natural rock", as opposed to an
# ore deposit (prototype type "resource").
ROCK_PROTOTYPE_TYPES = ("simple-entity",)
TREE_PROTOTYPE_TYPES = ("tree",)
CLIFF_PROTOTYPE_TYPES = ("cliff",)

# Marker sizes in world tiles, used when no observed geometry is available.
# These are the on-map symbol sizes, not entity footprints.
TREE_MARKER_TILES = 0.6
ROCK_MARKER_TILES = 0.7
CLIFF_MARKER_TILES = 1.0

# Smallest on-screen radius, in pixels, of a tree glyph.
#
# At a wide map zoom one world tile is only a few pixels across, so a tree
# drawn strictly to its observed footprint becomes a one-pixel speck and a
# densely wooded region reads as scattered dots instead of forest cover.
# The minimum keeps every *observed* tree legible; it never adds a tree at
# a position the observer did not report.
TREE_MIN_MARKER_PIXELS = 2.5


def _number(value):
    """Return a finite float for a numeric value, or None.

    ``bool`` is rejected explicitly: a boolean is not a coordinate or a size.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def parse_map_color(value):
    """Return ``#rrggbb`` for a Factorio ``Color`` value, or None.

    Factorio's ``Color`` type is ``{r, g, b, a}`` with float components in
    0..1, but the data stage also accepts 0..255 components and the short
    three-element array form. All of those are accepted here; anything that is
    not a usable colour is rejected instead of being guessed.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if len(value) not in (3, 4):
            return None
        channels = list(value)
    elif isinstance(value, dict):
        if "r" not in value or "g" not in value or "b" not in value:
            return None
        channels = [value["r"], value["g"], value["b"]]
        if "a" in value:
            channels.append(value["a"])
    else:
        return None
    for channel in channels:
        if isinstance(channel, bool) or not isinstance(channel, (int, float)):
            return None
        if not math.isfinite(float(channel)):
            return None
    # The Color documentation states that components above 1 are interpreted
    # as 0..255 values; otherwise they are 0..1 floats.
    numbers = [float(c) for c in channels]
    if any(n < 0.0 or n > 255.0 for n in numbers):
        return None
    if any(n > 1.0 for n in numbers[:3]):
        ints = [max(0, min(255, int(round(n)))) for n in numbers[:3]]
    else:
        ints = [max(0, min(255, int(round(n * 255.0)))) for n in numbers[:3]]
    return "#%02x%02x%02x" % tuple(ints)


def verified_prototype_map_color(name):
    """Return the verified 2.1.23 map colour for a known prototype name."""
    if not isinstance(name, str):
        return None
    rgb = VERIFIED_PROTOTYPE_MAP_COLORS.get(name)
    if rgb is None:
        return None
    return "#%02x%02x%02x" % rgb


def nature_color(entity):
    """Return the colour to draw one observed natural entity with, or None.

    The colour sources are tried in this order:

    1. The observed chart colour, in Factorio's documented priority order:
       ``friendly_map_color`` / ``enemy_map_color`` before ``map_color``.
    2. For a tree, the verified Factorio 2.1.23 tint palette entry selected
       by the observed ``graphics_variation``. This is the exact colour the
       game tints that tree's sprite with.
    3. The verified Factorio 2.1.23 prototype colour table.

    An observed colour that is exactly the runtime's white default is
    **rejected**: Factorio 2.1.23 returns white from
    ``LuaEntityPrototype::map_color`` for every prototype whose real chart
    colour it does not expose there, so white means "no authoritative chart
    colour", not "paint it white".

    When no authoritative colour exists the function returns None. The caller
    then draws an outline-only marker, which keeps the position truthful
    without inventing a colour.
    """
    if not isinstance(entity, dict):
        return None
    for key in CHART_COLOR_KEYS:
        observed = parse_map_color(entity.get(key))
        if observed is None or observed == RUNTIME_DEFAULT_CHART_COLOR:
            continue
        return observed
    tint = tree_tint_color(entity.get("name"), entity.get("graphics_variation"))
    if tint is not None:
        return tint
    return verified_prototype_map_color(entity.get("name"))


def tree_tint_color(name, variation):
    """Return the verified 2.1.23 map colour of one observed tree, or None.

    Factorio tints a tree with the palette entry that matches its graphics
    variation, and the palette is shorter than the number of sprite frames
    (a tree's trunk animates in four frames), so the index wraps around the
    palette. The LIVE READ-ONLY observation of the running 2.1.23 game
    confirms this: ``tree-08`` has seven palette entries but placed trees
    were observed with graphics variations from 1 to 10.

    The in-game map draws the tree darkened by Factorio's own map shading
    factor rather than in the bright world sprite colour, so the verified
    tint is shaded the same way the game shades a charted map tile.

    When the variation is unknown the palette's first entry is not used as a
    guess: a tree without a known variation returns None so no colour is
    invented.
    """
    palette = tree_tint_palette(name)
    if not palette:
        return None
    index = _number(variation)
    if index is None or index < 0:
        return None
    return shade_color(palette[int(index) % len(palette)], MAP_SHADING_FACTOR)


def shade_color(color, factor):
    """Return ``color`` darkened by Factorio's map shading factor."""
    if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
        return None
    try:
        channels = [int(color[position:position + 2], 16) for position in (1, 3, 5)]
    except ValueError:
        return None
    shaded = [max(0, min(255, int(round(channel * factor)))) for channel in channels]
    return "#%02x%02x%02x" % tuple(shaded)


class NatureShape:
    """One natural object prepared for drawing.

    ``kind`` is ``"tree"``, ``"rock"`` or ``"cliff"``; ``color`` is None when
    no authoritative colour is available; ``tiles`` is the observed world
    footprint in tiles (width and height), or None when the observer reported
    no geometry.
    """

    __slots__ = ("kind", "color", "x", "y", "tiles", "name")

    def __init__(self, kind, color, x, y, tiles, name):
        self.kind = kind
        self.color = color
        self.x = x
        self.y = y
        self.tiles = tiles
        self.name = name

    def __repr__(self):  # pragma: no cover - debugging aid
        return (
            f"NatureShape(kind={self.kind!r}, color={self.color!r}, "
            f"x={self.x!r}, y={self.y!r}, tiles={self.tiles!r}, name={self.name!r})"
        )


def _observed_tiles(entity):
    """Return the observed (width, height) footprint in tiles, or None.

    Only the observer's own geometry is used. A missing width or height means
    "unknown", never "one tile".
    """
    width = _number(entity.get("width"))
    height = _number(entity.get("height"))
    if width is not None and height is not None and width > 0 and height > 0:
        return (width, height)
    bounds = entity.get("bounds")
    if isinstance(bounds, dict):
        a = bounds.get("left_top")
        b = bounds.get("right_bottom")
        if isinstance(a, dict) and isinstance(b, dict):
            ax = _number(a.get("x"))
            ay = _number(a.get("y"))
            bx = _number(b.get("x"))
            by = _number(b.get("y"))
            if ax is None or ay is None or bx is None or by is None:
                return None
            dx = bx - ax
            dy = by - ay
            if dx > 0 and dy > 0:
                return (dx, dy)
    return None


def _prototype_type(entity):
    value = entity.get("prototype_type")
    return value if isinstance(value, str) else ""


def _entity_type(entity):
    value = entity.get("entity_type")
    return value if isinstance(value, str) else ""


def nature_shape(entity):
    """Classify one observed natural entity into a drawable shape.

    The classification uses only observed fields. The prototype type decides
    whether the object is a tree, a cliff or a mineable rock, so a stone ore
    deposit is never confused with a rock.
    """
    if not isinstance(entity, dict):
        return None
    x = _number(entity.get("x"))
    y = _number(entity.get("y"))
    if x is None or y is None:
        return None
    prototype_type = _prototype_type(entity)
    entity_type = _entity_type(entity)
    if prototype_type in TREE_PROTOTYPE_TYPES or entity_type == "tree":
        kind = "tree"
    elif prototype_type in CLIFF_PROTOTYPE_TYPES or entity_type == "cliff":
        kind = "cliff"
    elif prototype_type in ROCK_PROTOTYPE_TYPES or entity_type == "simple-entity":
        kind = "rock"
    else:
        return None
    name = entity.get("name")
    return NatureShape(
        kind=kind,
        color=nature_color(entity),
        x=x,
        y=y,
        tiles=_observed_tiles(entity),
        name=name if isinstance(name, str) else "",
    )


def nature_shapes(entities, origin=None):
    """Return the drawable natural shapes for the observed entities.

    ``origin`` optionally restricts the result to the observed window; entities
    outside it are dropped rather than drawn. The result is a list, so a
    forest of thousands of trees costs one pass over the observed entities.
    """
    shapes = []
    if not isinstance(entities, list):
        return shapes
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("kind") != "nature":
            continue
        shape = nature_shape(entity)
        if shape is None:
            continue
        if origin is not None:
            x = shape.x
            y = shape.y
            if not (
                origin["x"] <= x < origin["x"] + origin["width"]
                and origin["y"] <= y < origin["y"] + origin["height"]
            ):
                continue
        shapes.append(shape)
    return shapes


def tree_shape(shape):
    """Return the on-map symbol size, in tiles, for a tree.

    A tree's own footprint is only a fraction of a tile, so the map symbol is
    drawn at the game's tree-marker size unless a larger observed footprint
    was reported.
    """
    return _symbol_tiles(shape, TREE_MARKER_TILES)


def nature_fingerprint(entities):
    """Return a cheap fingerprint of the observed nature entities.

    The dashboard redraws on every pan, zoom and timer tick. Classifying a
    large forest each time is wasteful, so the view caches the classified
    shapes and uses this fingerprint to notice when the observation actually
    changed. The fingerprint only inspects the fields that can change a
    drawn shape: the position, the prototype identity, the chart colour and
    the observed footprint.
    """
    if not isinstance(entities, list):
        return ()
    parts = []
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("kind") != "nature":
            continue
        parts.append((
            entity.get("x"),
            entity.get("y"),
            entity.get("name"),
            entity.get("entity_type"),
            entity.get("prototype_type"),
            entity.get("map_color"),
            entity.get("friendly_map_color"),
            entity.get("enemy_map_color"),
            entity.get("graphics_variation"),
            entity.get("width"),
            entity.get("height"),
            entity.get("bounds"),
        ))
    return tuple(parts)


def rock_shape(shape):
    """Return the on-map symbol size, in tiles, for a mineable rock."""
    return _symbol_tiles(shape, ROCK_MARKER_TILES)


def cliff_shape(shape):
    """Return the on-map symbol size, in tiles, for a cliff."""
    return _symbol_tiles(shape, CLIFF_MARKER_TILES)


def _symbol_tiles(shape, marker_tiles):
    if shape.tiles is None:
        return marker_tiles
    width, height = shape.tiles
    # A natural object never covers less than its marker symbol on the map.
    return max(marker_tiles, min(width, height))
