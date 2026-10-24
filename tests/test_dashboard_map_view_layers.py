"""View-level tests for the dashboard map render order and patch layer.

These call the real drawing methods with a stub canvas, so no display and
no Factorio process is required.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_view import LiveView


class FakeCanvas:
    """Records the canvas calls a draw method makes."""

    def __init__(self):
        self.calls = []

    def create_rectangle(self, *args, **kwargs):
        self.calls.append(("rectangle", args, kwargs))

    def create_oval(self, *args, **kwargs):
        self.calls.append(("oval", args, kwargs))

    def create_text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def create_line(self, *args, **kwargs):
        self.calls.append(("line", args, kwargs))

    def create_polygon(self, *args, **kwargs):
        self.calls.append(("polygon", args, kwargs))

    def create_image(self, *args, **kwargs):
        self.calls.append(("image", args, kwargs))

    def delete(self, *args, **kwargs):
        self.calls.append(("delete", args, kwargs))

    def of(self, kind):
        return [c for c in self.calls if c[0] == kind]


class StubView:
    """Just enough of LiveView to drive the drawing helpers."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.layers = {"resource": _Truthy(True)}
        self.overlay_entries = {}
        self.offset = {"x": 0, "y": 0}
        self.last = None

    draw_resource_patches = LiveView.draw_resource_patches
    draw = LiveView.draw


class _Truthy:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def ore(x, y, name="iron-ore", **extra):
    entity = dict(x=x, y=y, name=name, kind="resource")
    entity.update(extra)
    return entity


class ResourcePatchRenderTests(unittest.TestCase):
    def render(self, entities, origin=None):
        canvas = FakeCanvas()
        view = StubView(canvas)
        terrain = dict(entities=entities)
        if origin:
            terrain["origin"] = origin
        view.draw_resource_patches(
            terrain, {"x": 0, "y": 0}, 800, 600, 60
        )
        return canvas

    def test_adjacent_deposits_render_as_one_filled_rectangle(self):
        canvas = self.render(
            [ore(0, 0), ore(1, 0), ore(2, 0)], origin=dict(x=-32, y=-32)
        )
        rects = canvas.of("rectangle")
        self.assertEqual(len(rects), 1)
        _, args, kwargs = rects[0]
        self.assertEqual(kwargs.get("fill"), "#6a8694")
        # No black per-deposit border.
        self.assertEqual(kwargs.get("outline"), "")

    def test_patches_are_not_drawn_as_ovals(self):
        canvas = self.render([ore(0, 0), ore(1, 0)], origin=dict(x=-32, y=-32))
        self.assertEqual(canvas.of("oval"), [])

    def test_separate_resources_get_separate_filled_rectangles(self):
        canvas = self.render(
            [ore(0, 0, "iron-ore"), ore(50, 50, "copper-ore")],
            origin=dict(x=-32, y=-32),
        )
        fills = {c[2].get("fill") for c in canvas.of("rectangle")}
        self.assertEqual(fills, {"#6a8694", "#cd6337"})

    def test_no_observed_resources_means_nothing_is_drawn(self):
        canvas = self.render([])
        self.assertEqual(canvas.of("rectangle"), [])

    def test_building_entities_are_not_part_of_the_patch_layer(self):
        canvas = self.render(
            [dict(x=0, y=0, name="assembling-machine-3", kind="building")],
            origin=dict(x=-32, y=-32),
        )
        self.assertEqual(canvas.of("rectangle"), [])

    def test_patch_covers_the_observed_tile_span(self):
        canvas = self.render([ore(0, 0), ore(1, 0)], origin=dict(x=-32, y=-32))
        _, args, _ = canvas.of("rectangle")[0]
        left, top, right, bottom = args[:4]
        # Radius 60 over an 800x600 viewport gives 5 pixels per tile.
        self.assertAlmostEqual(right - left, 2 * 5, places=6)
        self.assertAlmostEqual(bottom - top, 1 * 5, places=6)


if __name__ == "__main__":
    unittest.main()
