import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_feed import overlay_details


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.o = dict(schema=1, player_name="Engineer", available={}, partial={})
        for key in ("pollution", "electric", "logistics", "turrets", "stations", "tags"):
            self.o[key] = []
            self.o["available"][key] = True
            self.o["partial"][key] = False

    def check(self, o=None):
        return overlay_details({"overlays": o or self.o}, {"x": 0, "y": 0})["overlays"]

    def test_all_layers_and_empty_lua_tables(self):
        for key in self.o["available"]:
            self.o[key] = {}
        self.assertEqual(self.check()["electric"], [])

    def test_valid_data(self):
        self.o["pollution"] = [dict(x=0, y=0, width=32, height=32, value=12)]
        self.o["electric"] = [dict(x=1, y=1, radius=2.5, connections=[dict(x=3, y=3)])]
        self.o["logistics"] = [dict(x=1, y=1, logistic=25, construction=55, active=True)]
        self.o["turrets"] = [dict(x=1, y=1, radius=18)]
        self.o["stations"] = [dict(x=1, y=1, text="Station")]
        self.o["tags"] = [dict(x=1, y=1, text="", icon="iron-ore")]
        self.assertEqual(self.check()["tags"][0]["icon"], "iron-ore")

    def test_rejects_invalid_values_bounds_and_false_availability(self):
        for entry in [
            dict(x=-1, y=0, width=32, height=32, value=1),
            dict(x=250, y=0, width=32, height=32, value=1),
            dict(x=0, y=0, width=32, height=32, value=float("nan")),
            dict(x=0, y=0, width=True, height=32, value=1),
        ]:
            o = copy.deepcopy(self.o)
            o["pollution"] = [entry]
            with self.assertRaises(ValueError):
                self.check(o)
        self.o["available"]["turrets"] = False
        self.o["turrets"] = [dict(x=1, y=1, radius=18)]
        with self.assertRaises(ValueError):
            self.check()

    def test_caps_and_connector_endpoints(self):
        self.o["electric"] = [dict(x=1, y=1, radius=2, connections=[dict(x=256, y=0)])]
        with self.assertRaises(ValueError):
            self.check()
        self.o["electric"] = []
        self.o["tags"] = [dict(x=1, y=1, text="x", icon="")] * 129
        with self.assertRaises(ValueError):
            self.check()
