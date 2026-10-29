"""Generated blueprints must be R07-valid and based on observed machines."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from blueprint_design_engine import game_version_code, generate_draft
from blueprint_document import decode


def plan():
    return {
        "recipe": {"name": "iron-gear-wheel", "category": "crafting",
                   "categories": ["crafting"]},
        "machine": {"name": "assembling-machine-2",
                    "crafting_categories": ["crafting"], "crafting_speed": 0.75},
        "status": "estimated",
        "machine_count": 18,
        "target": {"name": "iron-gear-wheel", "per_minute": 500},
        "source_fingerprint": "game-observed-4",
        "game_version": "2.1.23",
    }


class DesignEngineTests(unittest.TestCase):
    def test_layout_is_decodable_with_machine_names_and_recipe(self):
        result = generate_draft(plan())
        self.assertEqual(result["status"], "draft_not_buildability_verified")
        doc = decode(result["exchange"])
        entities = doc["blueprint"]["entities"]
        self.assertEqual(len(entities), 18)
        self.assertEqual(len({(e["position"]["x"], e["position"]["y"]) for e in entities}), 18)
        self.assertTrue(all(e["recipe"] == "iron-gear-wheel" for e in entities))

    def test_game_version_comes_from_observation(self):
        self.assertEqual(game_version_code("2.1.23"), (2 << 48) | (1 << 32) | (23 << 16))
        with self.assertRaises(ValueError):
            game_version_code("future")

    def test_refuses_unobserved_machine_category(self):
        p = plan()
        p["machine"] = {"name": "alien-smelter", "crafting_categories": ["smelting"]}
        with self.assertRaisesRegex(ValueError, "category"):
            generate_draft(p)

    def test_refuses_nonqualified_and_oversized_layout(self):
        p = plan()
        p["machine_count"] = 99999
        with self.assertRaisesRegex(ValueError, "draft limit"):
            generate_draft(p)
        p["machine_count"] = 2
        p["source_fingerprint"] = None
        with self.assertRaisesRegex(ValueError, "fingerprinted"):
            generate_draft(p)

    def test_never_claims_working_in_game(self):
        result = generate_draft(plan())
        self.assertIn("not", result["status"])
        self.assertIn("power", result["warnings"][-2].lower())


class SpatialDesignEngineTests(unittest.TestCase):
    """The design engine uses the observed footprint when the game gave one."""

    def spatial_plan(self):
        p = plan()
        p["machine"] = {
            "name": "assembling-machine-2",
            "crafting_categories": ["crafting"],
            "crafting_speed": 0.75,
            "energy_usage": 90000.0,
            "size": {"width": 3, "height": 3},
            "direction": 0,
        }
        p["recipe"] = {
            "name": "iron-gear-wheel",
            "category": "crafting",
            "categories": ["crafting"],
            "crafting_time": 0.5,
            "ingredients": [{"name": "iron-plate", "amount": 2.0,
                             "type": "item"}],
            "products": [{"name": "iron-gear-wheel", "amount": 1.0,
                          "type": "item"}],
        }
        return p

    def test_observed_size_produces_a_spatial_draft(self):
        result = generate_draft(self.spatial_plan())
        self.assertEqual(result["status"], "draft_spatial_plan_validated")
        self.assertIn("layout", result)

    def test_spatial_draft_entities_do_not_overlap(self):
        result = generate_draft(self.spatial_plan())
        entities = result["document"]["blueprint"]["entities"]
        tiles = set()
        for entity in entities:
            width = 3
            height = 3
            left = entity["position"]["x"]
            top = entity["position"]["y"]
            for column in range(width):
                for row in range(height):
                    tile = (left + column, top + row)
                    self.assertNotIn(tile, tiles)
                    tiles.add(tile)

    def test_spatial_draft_reports_the_observed_flows(self):
        result = generate_draft(self.spatial_plan())
        layout = result["layout"]
        self.assertEqual(layout["inputs"][0]["item"], "iron-plate")
        self.assertEqual(layout["outputs"][0]["item"], "iron-gear-wheel")
        self.assertGreater(layout["power_watts"], 0)

    def test_spatial_draft_still_never_claims_buildability(self):
        result = generate_draft(self.spatial_plan())
        joined = " ".join(result["warnings"]).lower()
        self.assertIn("not verified", joined)
        self.assertIn("buildability", joined)

    def test_unusable_observed_size_keeps_the_grid_and_reports_it(self):
        p = self.spatial_plan()
        p["machine"]["size"] = {"width": 0, "height": 3}
        result = generate_draft(p)
        self.assertEqual(result["status"], "draft_not_buildability_verified")
        self.assertTrue(any("footprint" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
