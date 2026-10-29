"""Offline boundaries and receipt checks for the populated R10-B fixture."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import live_r10b_populated_fixture as fixture  # noqa: E402


class StubRcon:
    def __init__(self, receipts=None):
        self.calls = []
        self.receipts = receipts or {}

    def command(self, text):
        self.calls.append(text)
        if text.startswith("/c "):
            receipt = self.receipts.get("creative", {
                "player_surface": fixture.SURFACE,
                "surface": fixture.SURFACE,
                "networks_requested": 2,
            })
            return fixture.MARKER + json.dumps(receipt)
        operation = text.split()[1]
        return json.dumps(self.receipts.get(operation, {"status": "ok", "rows": []}))


class PopulatedFixtureContractTests(unittest.TestCase):
    def test_init_stays_on_named_disposable_surface(self):
        rcon = StubRcon()
        data = fixture.initialize(rcon, 2)
        self.assertEqual(data["player_surface"], fixture.SURFACE)
        self.assertIn("game.create_surface", rcon.calls[0])
        self.assertIn("p.teleport", rcon.calls[0])
        self.assertTrue(rcon.calls[0].startswith("/c "))
        self.assertNotIn("game.speed", rcon.calls[0])

    def test_network_counts_and_coordinates_are_bounded(self):
        with self.assertRaises(ValueError):
            fixture.construct_network(StubRcon(), 8)
        with self.assertRaises(ValueError):
            fixture.initialize(StubRcon(), 0)
        rcon = StubRcon({"creative": {
            "index": 1, "built": {}, "bots": 60, "iron": 4800,
            "copper": 1800, "rails": 31, "wagons": 3,
            "cargo_iron": 1800, "fluid_water": 15000,
        }})
        result = fixture.construct_network(rcon, 1)
        self.assertEqual(result["wagons"], 3)
        self.assertIn("cargo-wagon", rcon.calls[0])
        self.assertIn("fluid-wagon", rcon.calls[0])
        self.assertIn("roboport_robot", rcon.calls[0])
        self.assertIn("passive-provider-chest", rcon.calls[0])
        self.assertIn("direction=(n=='straight-rail'", rcon.calls[0])
        self.assertIn(f"x={100+fixture.CENTER_GAP}", rcon.calls[0])

    def test_registered_observation_requires_real_contents(self):
        rcon = StubRcon()
        with patch.object(fixture.time, "sleep", return_value=None):
            observed = fixture.verify_live(rcon, [])
        self.assertFalse(observed["contents_verified"])
        self.assertEqual([x.split()[1] for x in rcon.calls],
                         ["logistics", "robots", "transport",
                          "machine_inventories"])
        self.assertTrue(all(x.startswith("/autoengineer-observe ")
                            for x in rcon.calls))

    def test_exact_positive_inventory_and_robot_evidence(self):
        rcon = StubRcon({
            "logistics": {"status": "ok", "total": 1, "rows": [{
                "network_id": 7, "items": [
                    {"name": "iron-plate", "count": 400},
                    {"name": "copper-plate", "count": 150}],
            }]},
            "robots": {"status": "ok", "total_logistic_robots": 40,
                       "total_construction_robots": 25},
            "transport": {"status": "ok", "total": 2, "rows": [
                {"type": "cargo-wagon", "inventories": [
                    {"items": [{"name": "iron-plate", "count": 900}]}]},
                {"type": "fluid-wagon", "fluids": [
                    {"name": "water", "amount": 15000}]},
            ]},
            "machine_inventories": {"status": "ok", "row_count": 7},
        })
        with patch.object(fixture.time, "sleep", return_value=None):
            observed = fixture.verify_live(rcon, [
                {"wagons": 2, "rails": 25, "bots": 65}])
        self.assertTrue(observed["contents_verified"])
        self.assertEqual(observed["logistic_contents"]["iron-plate"], 400)
        self.assertEqual(observed["built_rails"], 25)
        self.assertTrue(observed["wagon_water_found"])


if __name__ == "__main__":
    unittest.main()
