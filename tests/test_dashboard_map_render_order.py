"""Render-order and geometry tests for the live dashboard map.

The map must read like the Factorio in-game map:

1. charted terrain underneath,
2. resource patches above the terrain,
3. buildings above the patches, at their exact observed footprints,
4. the player marker and labels above everything else.

These tests drive the real ``LiveView.draw`` with a recording canvas, so no
display and no Factorio process is needed.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_view import LiveView


class RecordingCanvas:
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
        return [c for c in self.calls if c[0] == kind]

    def index_of(self, predicate):
        for index, call in enumerate(self.calls):
            if predicate(call):
                return index
        return -1


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class StubView:
    """Just enough of LiveView to drive ``draw`` without a Tk root."""

    def __init__(self, canvas, frame):
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
        self.zoom = Var("60")
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


def frame(entities=(), tiles=(), position=None):
    return {
        "position": position or {"x": 0, "y": 0},
        "terrain": {
            "origin": {"x": -32, "y": -32},
            "step": 2,
            "tiles": list(tiles),
            "entities": list(entities),
            "partial": False,
        },
        "visited": [],
        "failed": [],
        "objective": None,
        "proposal": None,
        "surface": "nauvis",
        "tick": 1,
    }


def ore(x, y, name="iron-ore", **extra):
    entity = dict(x=x, y=y, name=name, kind="resource")
    entity.update(extra)
    return entity


def building(x, y, name="assembling-machine-3", **extra):
    entity = dict(x=x, y=y, name=name, kind="building")
    entity.update(extra)
    return entity


class RenderOrderTests(unittest.TestCase):
    def render(self, data):
        canvas = RecordingCanvas()
        view = StubView(canvas, data)
        view.draw()
        return canvas

    def test_terrain_is_drawn_before_the_resource_patch(self):
        canvas = self.render(
            frame(entities=[ore(0, 0)], tiles=[dict(x=0, y=0, name="grass-1")])
        )
        terrain_index = canvas.index_of(
            lambda c: c[0] == "rectangle" and c[2].get("fill") == "#59653b"
        )
        patch_index = canvas.index_of(
            lambda c: c[0] == "rectangle" and c[2].get("fill") == "#6a8694"
        )
        self.assertGreaterEqual(terrain_index, 0)
        self.assertGreaterEqual(patch_index, 0)
        self.assertLess(terrain_index, patch_index)

    def test_resource_patch_is_drawn_before_the_building(self):
        canvas = self.render(
            frame(
                entities=[
                    ore(0, 0),
                    building(10, 10, width=3.0, height=3.0),
                ]
            )
        )
        patch_index = canvas.index_of(
            lambda c: c[0] == "rectangle" and c[2].get("fill") == "#6a8694"
        )
        building_index = canvas.index_of(
            lambda c: c[0] == "rectangle" and c[2].get("fill") == "#67acc2"
        )
        self.assertGreaterEqual(patch_index, 0)
        self.assertGreaterEqual(building_index, 0)
        self.assertLess(patch_index, building_index)

    def test_player_marker_is_drawn_last(self):
        canvas = self.render(frame(entities=[ore(0, 0), building(10, 10)]))
        player_index = canvas.index_of(lambda c: c[0] == "polygon")
        building_index = canvas.index_of(
            lambda c: c[0] == "rectangle" and c[2].get("fill") == "#67acc2"
        )
        self.assertGreaterEqual(player_index, 0)
        self.assertLess(building_index, player_index)

    def test_resources_are_not_drawn_as_outlined_ovals(self):
        canvas = self.render(frame(entities=[ore(0, 0), ore(1, 0), ore(2, 0)]))
        self.assertEqual(canvas.of("oval"), [])
        for call in canvas.of("rectangle"):
            self.assertNotEqual(call[2].get("fill"), "#be92b9")

    def test_no_patch_is_drawn_without_observed_resources(self):
        canvas = self.render(frame(entities=[building(10, 10)]))
        self.assertEqual(
            [c for c in canvas.of("rectangle") if c[2].get("fill") == "#6a8694"], []
        )


class BuildingFootprintTests(unittest.TestCase):
    def render(self, data):
        canvas = RecordingCanvas()
        view = StubView(canvas, data)
        view.draw()
        return canvas

    def building_rect(self, canvas):
        found = [
            c for c in canvas.of("rectangle") if c[2].get("fill") == "#67acc2"
        ]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_building_uses_the_exact_observed_bounds(self):
        canvas = self.render(
            frame(
                entities=[
                    building(
                        10,
                        10,
                        bounds={
                            "left_top": {"x": 9.5, "y": 9.0},
                            "right_bottom": {"x": 12.5, "y": 11.0},
                        },
                    )
                ]
            )
        )
        _, args, _ = self.building_rect(canvas)
        left, top, right, bottom = args[:4]
        # Radius 60 over an 800x600 viewport is 5 pixels per tile.
        self.assertAlmostEqual(right - left, 3.0 * 5, places=6)
        self.assertAlmostEqual(bottom - top, 2.0 * 5, places=6)

    def test_building_uses_observed_width_and_height(self):
        canvas = self.render(
            frame(entities=[building(10, 10, width=3.0, height=2.0)])
        )
        _, args, _ = self.building_rect(canvas)
        left, top, right, bottom = args[:4]
        self.assertAlmostEqual(right - left, 3.0 * 5, places=6)
        self.assertAlmostEqual(bottom - top, 2.0 * 5, places=6)

    def test_building_without_observed_geometry_stays_a_symbol(self):
        canvas = self.render(frame(entities=[building(10, 10)]))
        ovals = canvas.of("oval")
        self.assertEqual(len(ovals), 1)
        self.assertEqual(ovals[0][2].get("fill"), "#67acc2")
        self.assertEqual(
            [c for c in canvas.of("rectangle") if c[2].get("fill") == "#67acc2"], []
        )

    def test_building_geometry_is_never_inferred_from_the_name(self):
        # Two differently named machines with no observed geometry produce the
        # same symbol shape: nothing is derived from the prototype name.
        first = self.render(frame(entities=[building(10, 10, name="furnace")]))
        second = self.render(
            frame(entities=[building(10, 10, name="assembling-machine-3")])
        )
        self.assertEqual(first.of("oval")[0][1], second.of("oval")[0][1])


if __name__ == "__main__":
    unittest.main()
