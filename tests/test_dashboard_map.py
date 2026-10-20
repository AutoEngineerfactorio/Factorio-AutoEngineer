import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_feed import PREFIX, DashboardFeed, parse_frame, snapshot
from dashboard_view import project, terrain_color


def frame() -> dict[str, Any]:
    return dict(
        status="ok",
        x=0,
        y=0,
        tick=1,
        surface="nauvis",
        inventory=[],
        inventory_available=True,
        truncated=False,
        slots=[dict(slot=3, name="iron-plate", quality="rare", count=8)],
        capacity=80,
        slots_truncated=False,
        terrain=dict(
            origin=dict(x=-32, y=-32),
            step=2,
            tiles=[dict(x=0, y=0, name="water")],
            entities=[dict(x=1, y=1, name="iron-ore", kind="resource")],
            partial=False,
        ),
    )


class MapTests(unittest.TestCase):
    def test_roundtrip_preserves_slot_and_quality(self):
        d = snapshot(frame())
        d.update(DashboardFeed().features)
        f = parse_frame(PREFIX + json.dumps(dict(schema=1, status="ok", **d)))
        assert f is not None
        self.assertEqual(f["slots"][0], dict(slot=3, name="iron-plate", quality="rare", count=8))
        self.assertEqual(f["capacity"], 80)
        self.assertEqual(f["terrain"]["tiles"][0]["name"], "water")

    def test_unknown_terrain_and_empty_slots(self):
        d = frame()
        d["terrain"]["tiles"] = {}
        d["terrain"]["entities"] = {}
        d["slots"] = {}
        self.assertEqual(snapshot(d)["slots"], [])

    def test_invalid_or_unbounded_observations(self):
        for mutate in [
            lambda d: d.update(capacity=True),
            lambda d: d["slots"][0].update(slot=81),
            lambda d: d["slots"].append(dict(d["slots"][0])),
            lambda d: d["terrain"]["tiles"][0].update(x=100),
            lambda d: d["terrain"]["entities"][0].update(kind="execute"),
            lambda d: d["terrain"].update(tiles=[dict(x=0, y=0, name="x")] * 1025),
            lambda d: d["slots"][0].update(name="bad\nname"),
        ]:
            d = frame()
            mutate(d)
            with self.assertRaises(ValueError):
                snapshot(d)

    def test_panning_projection_and_water_color(self):
        self.assertEqual(project(dict(x=10, y=10), dict(x=10, y=10), 400, 200, 50), (200, 100))
        self.assertNotEqual(terrain_color("deepwater"), terrain_color("grass-1"))
