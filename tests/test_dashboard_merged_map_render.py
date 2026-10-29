"""Regression tests for the merged multi-chunk map render path.

The dashboard renders a multi-chunk map through one production path:
``dashboard_view.merged_terrain`` turns the observer's merged "map" payload
into the shape the map layers expect, and ``LiveView.draw`` then paints the
terrain, the resource patches and the natural objects on top of it. That
merged path had no test coverage at all, so a defect in it could only be
found by looking at a live window. These tests drive the *real* functions
with a recording canvas, so no display and no Factorio process is needed.

Truthfulness rules checked here:

* A merged frame keeps every entity field the patch functions need, so an
  observed ore field still produces a filled patch rectangle.
* The patch layers must never paint a tile in a chunk that was never
  observed. The merged frame describes a set of observed chunks, and a chunk
  that is missing from that set is unexplored space: the game shows it
  black, and so must the dashboard.
* A resource node belongs to a chunk by its observed *position*. Its
  observed footprint may cross a chunk seam: the part of the footprint in a
  neighbouring chunk is kept when that chunk was observed, and dropped when
  it was not. A seam-crossing node is never painted twice.
"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from dashboard_chunk_grid import CHUNK_TILES  # noqa: E402
from dashboard_map_layers import (  # noqa: E402
    observed_chunk_tile_set,
    resource_patch_rectangles,
)
from dashboard_view import LiveView, map_scale, merged_terrain  # noqa: E402


class RecordingCanvas:
    """A canvas that records every drawing call instead of drawing it."""

    def __init__(self, width=800, height=600):
        self.calls = []
        self._width = width
        self._height = height

    def winfo_width(self):
        return self._width

    def winfo_height(self):
        return self._height

    def _record(self, kind, args, kwargs):
        self.calls.append((kind, args, kwargs))

    def create_rectangle(self, *args, **kwargs):
        self._record("rectangle", args, kwargs)

    def create_oval(self, *args, **kwargs):
        self._record("oval", args, kwargs)

    def create_text(self, *args, **kwargs):
        self._record("text", args, kwargs)

    def create_line(self, *args, **kwargs):
        self._record("line", args, kwargs)

    def create_polygon(self, *args, **kwargs):
        self._record("polygon", args, kwargs)

    def create_image(self, *args, **kwargs):
        self._record("image", args, kwargs)

    def delete(self, *args, **kwargs):
        self._record("delete", args, kwargs)

    def of(self, kind):
        return [call for call in self.calls if call[0] == kind]


class Var:
    """Just enough of a tk variable for the view under test."""

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class StubView:
    """Just enough of LiveView to drive ``draw`` without a Tk root."""

    def __init__(self, canvas, frame, zoom="128"):
        self.canvas = canvas
        self.layers = {
            "resource": Var(True),
            "nature": Var(True),
            "building": Var(True),
            "enemy": Var(True),
            "history": Var(False),
            "goals": Var(False),
            "grid": Var(False),
            "player_name": Var(False),
        }
        self.overlay_entries = {}
        self.offset = {"x": 0, "y": 0}
        self.zoom = Var(zoom)
        self.last = frame
        self.raster_key = None
        self.map_image = None

    draw = LiveView.draw
    draw_raster = LiveView.draw_raster
    draw_resource_patches = LiveView.draw_resource_patches
    draw_nature = LiveView.draw_nature
    _nature_shape_cache = LiveView._nature_shape_cache
    _draw_tree = LiveView._draw_tree
    _draw_rock = LiveView._draw_rock
    _draw_cliff = LiveView._draw_cliff


def ore(x, y, name="iron-ore", **extra):
    """One observed ore node."""
    entity = dict(x=x, y=y, name=name, kind="resource")
    entity.update(extra)
    return entity


def merged_frame(origins, entities, position=None):
    """A frame in the shape the observer publishes for a merged map."""
    return {
        "position": position or {"x": 0, "y": 0},
        "terrain": {"origin": {"x": 0, "y": 0}, "step": 2, "tiles": []},
        "map": {
            "surface": "nauvis",
            "origins": [tuple(origin) for origin in origins],
            "entities": list(entities),
            "tiles": [],
            "rasters": [],
            "partial": False,
        },
        "visited": [],
        "failed": [],
        "objective": None,
        "proposal": None,
        "surface": "nauvis",
        "tick": 1,
    }


def dense_field(x0, y0, x1, y1, name="iron-ore"):
    """A solid block of observed ore nodes covering the given tile range."""
    return [
        ore(x + 0.5, y + 0.5, name=name)
        for x in range(x0, x1 + 1)
        for y in range(y0, y1 + 1)
    ]


def render(frame, zoom="128"):
    """Drive the real LiveView.draw and return the recording canvas."""
    canvas = RecordingCanvas()
    view = StubView(canvas, frame, zoom=zoom)
    view.draw()
    return canvas


def patch_rectangles(canvas, color="#6a8694"):
    """Every filled resource-patch rectangle the view painted."""
    return [
        call
        for call in canvas.of("rectangle")
        if call[2].get("fill") == color and call[2].get("tags") == "resource-patch"
    ]


def painted_world_tiles(canvas, center=None, width=800, height=600, radius=128.0):
    """Return the world tiles covered by the painted resource patches.

    The screen rectangles are projected back onto the world grid with the
    same arithmetic the view used, so the assertion speaks the same
    language as the observer's chunk grid. The rectangle edges are the
    world coordinates of the tile borders, so the covered tiles are
    exact and no margin is added.
    """
    center = center or {"x": 0, "y": 0}
    scale = map_scale(width, height, radius)
    tiles = set()
    for call in patch_rectangles(canvas):
        left, top, right, bottom = call[1][:4]
        x0 = (left - width / 2) / scale + center["x"]
        y0 = (top - height / 2) / scale + center["y"]
        x1 = (right - width / 2) / scale + center["x"]
        y1 = (bottom - height / 2) / scale + center["y"]
        for tile_x in range(math.floor(x0), math.ceil(x1)):
            for tile_y in range(math.floor(y0), math.ceil(y1)):
                tiles.add((tile_x, tile_y))
    return tiles


def chunk_of(x, y):
    """The chunk index that contains a world tile."""
    return (x // CHUNK_TILES, y // CHUNK_TILES)


def _covers_tile(rect, tile):
    """True when a screen rectangle covers the given world tile.

    The rectangle corners are projected back onto the world grid with the
    same arithmetic the view used, so the check speaks the observer's chunk
    grid language.
    """
    left, top, right, bottom = rect
    scale = map_scale(800, 600, 128.0)
    x0 = (left - 800 / 2) / scale
    y0 = (top - 600 / 2) / scale
    x1 = (right - 800 / 2) / scale
    y1 = (bottom - 600 / 2) / scale
    return (
        math.floor(x0) <= tile[0] < math.ceil(x1)
        and math.floor(y0) <= tile[1] < math.ceil(y1)
    )


def paint_counts(canvas, center=None, width=800, height=600, radius=128.0):
    """Return how many times each world tile was painted.

    A tile covered by two painted rectangles was painted twice, which is a
    duplication defect: the same observed ore must be drawn once.
    """
    center = center or {"x": 0, "y": 0}
    scale = map_scale(width, height, radius)
    counts = {}
    for call in patch_rectangles(canvas):
        left, top, right, bottom = call[1][:4]
        x0 = (left - width / 2) / scale + center["x"]
        y0 = (top - height / 2) / scale + center["y"]
        x1 = (right - width / 2) / scale + center["x"]
        y1 = (bottom - height / 2) / scale + center["y"]
        for tile_x in range(math.floor(x0), math.ceil(x1)):
            for tile_y in range(math.floor(y0), math.ceil(y1)):
                key = (tile_x, tile_y)
                counts[key] = counts.get(key, 0) + 1
    return counts


class MergedTerrainShapeTests(unittest.TestCase):
    """The merged frame must keep what the map layers need."""

    def test_a_merged_frame_produces_the_layer_shape(self):
        terrain = merged_terrain(merged_frame([(0, 0), (2, 2)], [ore(1.5, 2.5)]))
        self.assertIn("entities", terrain)
        self.assertIn("rasters", terrain)
        self.assertIn("origin", terrain)
        self.assertIn("width", terrain)
        self.assertIn("height", terrain)
        self.assertIn("partial", terrain)
        self.assertFalse(terrain["partial"])

    def test_a_merged_frame_keeps_every_entity_field_the_patch_functions_need(self):
        entity = ore(
            5.5,
            6.5,
            name="copper-ore",
            width=2.0,
            height=3.0,
            bounds={
                "left_top": {"x": 4.5, "y": 5.0},
                "right_bottom": {"x": 6.5, "y": 8.0},
            },
        )
        terrain = merged_terrain(merged_frame([(0, 0)], [entity]))
        merged_entity = terrain["entities"][0]
        for field in ("kind", "name", "x", "y", "bounds", "width", "height"):
            self.assertIn(field, merged_entity)
        self.assertEqual(merged_entity["kind"], "resource")
        self.assertEqual(merged_entity["name"], "copper-ore")
        self.assertEqual(merged_entity["x"], 5.5)
        self.assertEqual(merged_entity["y"], 6.5)
        self.assertEqual(merged_entity["bounds"], entity["bounds"])
        self.assertEqual(merged_entity["width"], 2.0)
        self.assertEqual(merged_entity["height"], 3.0)

    def test_a_merged_frame_with_observed_ore_yields_an_ore_patch_rectangle(self):
        entities = dense_field(10, 10, 13, 13)
        terrain = merged_terrain(merged_frame([(0, 0), (1, 1)], entities))
        window = {
            "x": terrain["origin"]["x"],
            "y": terrain["origin"]["y"],
            "width": terrain["width"],
            "height": terrain["height"],
        }
        rectangles = resource_patch_rectangles(terrain["entities"], window)
        self.assertIn("iron-ore", rectangles)
        self.assertTrue(rectangles["iron-ore"])
        covered = set()
        for x0, y0, x1, y1 in rectangles["iron-ore"]:
            for tile_x in range(x0, x1 + 1):
                for tile_y in range(y0, y1 + 1):
                    covered.add((tile_x, tile_y))
        for tile_x in range(10, 14):
            for tile_y in range(10, 14):
                self.assertIn((tile_x, tile_y), covered)


class MergedMapRenderTests(unittest.TestCase):
    """The real draw path must paint a merged multi-chunk frame."""

    def test_a_merged_multi_chunk_frame_paints_a_resource_patch(self):
        entities = dense_field(10, 10, 13, 13)
        entities += dense_field(70, 70, 73, 73)
        canvas = render(merged_frame([(0, 0), (1, 1)], entities))
        painted = patch_rectangles(canvas)
        self.assertTrue(
            painted,
            "the merged multi-chunk frame painted no resource-patch rectangle",
        )

    def test_the_painted_patch_covers_the_observed_ore(self):
        entities = dense_field(10, 10, 13, 13)
        entities += dense_field(70, 70, 73, 73)
        canvas = render(merged_frame([(0, 0), (1, 1)], entities))
        tiles = painted_world_tiles(canvas)
        for tile_x in range(10, 14):
            for tile_y in range(10, 14):
                self.assertIn((tile_x, tile_y), tiles)
        for tile_x in range(70, 74):
            for tile_y in range(70, 74):
                self.assertIn((tile_x, tile_y), tiles)

    def test_a_contiguous_merge_paints_only_observed_chunks(self):
        entities = dense_field(10, 10, 13, 13)
        entities += dense_field(70, 70, 73, 73)
        canvas = render(merged_frame([(0, 0), (1, 1)], entities))
        tiles = painted_world_tiles(canvas)
        for tile_x, tile_y in tiles:
            self.assertIn(chunk_of(tile_x, tile_y), {(0, 0), (1, 1)})

    def test_a_merged_frame_without_ore_paints_no_resource_patch(self):
        canvas = render(merged_frame([(0, 0), (1, 1)], []))
        self.assertEqual(patch_rectangles(canvas), [])


class MergedChunkTruthfulnessTests(unittest.TestCase):
    """A chunk that was never observed must stay unpainted.

    ``merged_terrain`` derives one bounding box from every cached chunk
    origin. For a *non-contiguous* chunk set such as ``(0, 0)`` and
    ``(2, 2)`` that box is ``[0, 192) x [0, 192)`` tiles, which contains
    chunks ``(0, 1)``, ``(1, 0)``, ``(1, 1)`` and ``(2, 0)`` that were never
    observed. The patch and nature layers clip against that box, so the box
    permits tiles in unexplored space instead of forbidding them. The
    observer reports an ore node's real observed footprint, and a node on a
    chunk seam reports bounds that cross the seam, so that footprint is
    painted into the neighbouring, never-observed chunk.
    """

    def test_ore_never_lands_in_an_unobserved_chunk_of_a_non_contiguous_merge(self):
        observed_chunks = {(0, 0), (2, 2)}
        # An ore node in chunk (0, 0) whose observed bounds cross the seam
        # into chunk (1, 0), which was never observed.
        seam_node = ore(
            63.5,
            10.5,
            bounds={
                "left_top": {"x": 63.0, "y": 10.0},
                "right_bottom": {"x": 65.0, "y": 11.0},
            },
        )
        entities = [seam_node]
        entities += dense_field(128, 128, 131, 131)

        canvas = render(merged_frame(sorted(observed_chunks), entities))
        painted = painted_world_tiles(canvas)

        unobserved = set()
        for chunk_x in range(0, 3):
            for chunk_y in range(0, 3):
                if (chunk_x, chunk_y) not in observed_chunks:
                    unobserved.add((chunk_x, chunk_y))

        leaked = sorted(
            (tile_x, tile_y)
            for tile_x, tile_y in painted
            if chunk_of(tile_x, tile_y) in unobserved
        )
        self.assertEqual(
            leaked,
            [],
            "ore was painted in chunks that were never observed: "
            f"{leaked}; observed chunks were {sorted(observed_chunks)}, "
            f"unobserved chunks were {sorted(unobserved)}; "
            f"painted resource-patch rectangles were "
            f"{[call[1][:4] for call in patch_rectangles(canvas)]}",
        )

    def test_the_merged_window_does_not_admit_an_unobserved_chunk(self):
        """The reported window must not claim more than was observed.

        The window that ``merged_terrain`` reports describes the extent of the
        merged map, so a consumer that only reads width/height sees the whole
        map instead of a one-chunk window. It is a *bounding box* around the
        observed chunks, and for a non-contiguous chunk set that box also
        contains chunks that were never observed.

        The barrier that stops the patch layers from painting those chunks is
        the observed-chunk set itself: the chunk-aware clip keeps only the
        tiles that lie inside an observed chunk. So the invariant is asserted
        against the admitted *tile* set of that clip, which is the mechanism
        that actually protects unexplored space.
        """
        observed_chunks = {(0, 0), (2, 2)}
        terrain = merged_terrain(merged_frame(sorted(observed_chunks), []))
        window = {
            "x": terrain["origin"]["x"],
            "y": terrain["origin"]["y"],
            "width": terrain["width"],
            "height": terrain["height"],
        }
        # The window must cover every observed chunk, so a consumer that only
        # reads width/height is not handed a one-chunk window.
        for chunk_x, chunk_y in observed_chunks:
            tile_x = chunk_x * CHUNK_TILES
            tile_y = chunk_y * CHUNK_TILES
            self.assertTrue(
                window["x"] <= tile_x < window["x"] + window["width"]
                and window["y"] <= tile_y < window["y"] + window["height"],
                f"the merged window does not cover the observed chunk "
                f"{(chunk_x, chunk_y)}; window was {window}",
            )
        # The barrier that protects unexplored space is the observed-chunk
        # set: it must describe exactly the observed chunks, and the
        # chunk-aware clip may only admit tiles inside them.
        observed_keys = {
            (chunk["x"], chunk["y"])
            for chunk in (terrain.get("observed_chunks") or [])
        }
        self.assertEqual(observed_keys, observed_chunks)
        allowed = observed_chunk_tile_set(
            terrain.get("observed_chunks") or [], CHUNK_TILES
        )
        unobserved_tiles = set()
        for chunk_x in range(-1, 4):
            for chunk_y in range(-1, 4):
                if (chunk_x, chunk_y) in observed_chunks:
                    continue
                for ty in range(chunk_y * CHUNK_TILES, (chunk_y + 1) * CHUNK_TILES):
                    for tx in range(chunk_x * CHUNK_TILES, (chunk_x + 1) * CHUNK_TILES):
                        unobserved_tiles.add((tx, ty))
        leaked = sorted(allowed & unobserved_tiles)
        self.assertEqual(
            leaked,
            [],
            "the chunk-aware clip admits tiles in chunks that were never "
            f"observed: {leaked}; observed chunks were {sorted(observed_chunks)}",
        )
        self.assertEqual(
            terrain.get("observed_chunks"),
            [
                {"x": chunk_x, "y": chunk_y}
                for chunk_x, chunk_y in sorted(observed_chunks)
            ],
        )


class SeamCrossingResourceTests(unittest.TestCase):
    """A seam-crossing ore node keeps its observed footprint, exactly once.

    The observer reports an ore node's real observed bounding box. A node
    that sits on a chunk seam has a footprint that covers tiles in two
    chunks. Those tiles are legitimate observed data, so the renderer must
    keep them, but only the part of the footprint that lies in a chunk the
    observer actually reported.

    The renderer therefore has to decide two things separately: which chunk
    an entity belongs to (its observed *position*), and which of its tiles
    may be painted (the union of the observed chunks). Deciding both from
    the tile alone truncates one observed deposit into two separate patches
    at every seam, because the grouping and gap-fill then run once per
    chunk window instead of once over the observed map.
    """

    def seam_node(self):
        """An observed ore node in chunk (0, 0) whose bounds cross the seam.

        The node's position is x=63.5, so the node belongs to chunk (0, 0)
        by position. Its observed bounds cover tiles 63 and 64, and tile 64
        lies in chunk (1, 0).
        """
        return ore(
            63.5,
            10.5,
            bounds={
                "left_top": {"x": 63.0, "y": 10.0},
                "right_bottom": {"x": 65.0, "y": 11.0},
            },
        )

    def seam_field(self):
        """An observed ore deposit that straddles the seam at x=64.

        The nodes cover tiles x=60..67 and y=10..14, so the deposit is one
        observed field that spans chunks (0, 0) and (1, 0).
        """
        return dense_field(60, 10, 67, 14)

    def test_a_seam_crossing_node_keeps_its_footprint_when_both_chunks_are_observed(self):
        """Both chunks observed -> the node's tiles are painted exactly once.

        The tile in the neighbouring chunk is part of the observed node, so
        it is painted; and the node is visited once, through the chunk its
        position falls in, so no tile is painted twice.
        """
        canvas = render(merged_frame([(0, 0), (1, 0)], [self.seam_node()]))
        painted = painted_world_tiles(canvas)

        self.assertIn(
            (63, 10),
            painted,
            "the seam-crossing node lost the tile on its own side of the seam: "
            f"painted tiles were {sorted(painted)}",
        )
        self.assertIn(
            (64, 10),
            painted,
            "the seam-crossing node lost the observed tile in the neighbouring "
            f"observed chunk: painted tiles were {sorted(painted)}",
        )

        # No duplication: each of the node's tiles was painted exactly once.
        counts = paint_counts(canvas)
        for tile in ((63, 10), (64, 10)):
            self.assertEqual(
                counts.get(tile),
                1,
                f"tile {tile} was painted {counts.get(tile)} times instead of "
                f"once: rectangles were {[c[1][:4] for c in patch_rectangles(canvas)]}",
            )

    def test_an_observed_deposit_is_not_split_at_a_chunk_seam(self):
        """One observed deposit stays one patch across an observed seam.

        The observed field straddles the seam between the two observed
        chunks. A clip that groups and fills per chunk window cuts that one
        observed deposit into two patches, which is the seam-crossing
        observed footprint being truncated.
        """
        canvas = render(merged_frame([(0, 0), (1, 0)], self.seam_field()))
        rectangles = patch_rectangles(canvas)

        self.assertEqual(
            len(rectangles),
            1,
            "the observed deposit was split into several patches at the chunk "
            f"seam: rectangles were {[c[1][:4] for c in rectangles]}",
        )
        counts = paint_counts(canvas)
        duplicated = sorted(tile for tile, n in counts.items() if n != 1)
        self.assertEqual(
            duplicated,
            [],
            "tiles of the observed deposit were painted more than once: "
            f"{duplicated}",
        )
        # Every observed tile of the field is painted.
        for tile_x in range(60, 68):
            for tile_y in range(10, 15):
                self.assertIn(
                    (tile_x, tile_y),
                    counts,
                    f"the observed deposit lost the tile {(tile_x, tile_y)}: "
                    f"painted tiles were {sorted(counts)}",
                )

    def test_a_seam_crossing_node_keeps_no_tile_in_an_unobserved_chunk(self):
        """Only one chunk observed -> the unobserved neighbour stays empty.

        The node's position is in the observed chunk, so the node is kept,
        but the part of its footprint that lies in the unobserved neighbour
        is dropped: unexplored space must not show an ore tile.
        """
        canvas = render(merged_frame([(0, 0)], [self.seam_node()]))
        painted = painted_world_tiles(canvas)

        self.assertIn(
            (63, 10),
            painted,
            "the observed part of the seam-crossing node was not painted: "
            f"painted tiles were {sorted(painted)}",
        )
        self.assertNotIn(
            (64, 10),
            painted,
            "ore leaked into the unobserved neighbouring chunk: "
            f"painted tiles were {sorted(painted)}",
        )
        leaked = sorted(
            (tile_x, tile_y)
            for tile_x, tile_y in painted
            if chunk_of(tile_x, tile_y) != (0, 0)
        )
        self.assertEqual(
            leaked,
            [],
            "ore was painted outside the only observed chunk: "
            f"{leaked}; painted tiles were {sorted(painted)}",
        )
        # No duplication: the node is drawn once, not once per chunk.
        self.assertEqual(
            len(patch_rectangles(canvas)),
            1,
            "the seam-crossing node was painted more than once: "
            f"rectangles were {[c[1][:4] for c in patch_rectangles(canvas)]}",
        )


if __name__ == "__main__":
    unittest.main()
