import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from planning_view import catalog_view_model


class CatalogViewModelTests(unittest.TestCase):
    def test_lists_observed_item_and_fluid_recipe_data(self):
        recipe = {
            "name": "sulfuric-acid",
            "enabled": True,
            "hidden": False,
            "simple": False,
            "category": "chemistry",
            "crafting_time": 1.0,
            "ingredients": [
                {"name": "water", "type": "fluid", "amount": 100},
                {"name": "iron-plate", "type": "item", "amount": 1},
            ],
            "products": [{"name": "sulfuric-acid", "type": "fluid", "amount": 50}],
            "unlock_technologies": [
                {"name": "oil-processing", "researched": True, "enabled": True},
                {"name": "advanced-oil-processing", "researched": False, "enabled": True},
            ],
        }
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Planning disabled: profile is not qualified",
            "catalog_status": {
                "status": "assembled",
                "total_count": 1,
            },
            "capabilities": {
                "game_version": "2.0.77",
                "force": "player",
                "surface": "nauvis",
                "tick": 900,
                "enabled_content": ["base"],
                "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
                "recipes": [recipe],
                "research": ["oil-processing"],
            },
            "mechanics": {
                "categories_with_evidence": 3,
                "total_categories": 13,
                "dimension_counts": {
                    "observed": 3,
                    "verified": 0,
                    "regression_passed": 0,
                },
            },
        })

        self.assertIn("Planning disabled", model["status"])
        self.assertIn("Complete catalog: 1 recipes", model["metadata"])
        self.assertIn("Source change fingerprint:", model["metadata"])
        self.assertIn("(not authentication)", model["metadata"])
        self.assertIn("3/13 categories have evidence", model["metadata"])
        self.assertEqual(model["research"], ["oil-processing"])
        self.assertEqual(model["recipes"][0]["availability"], "Enabled")
        self.assertEqual(
            model["recipes"][0]["ingredients"],
            "100 fluid:water, 1 item:iron-plate",
        )
        self.assertEqual(model["recipes"][0]["products"], "50 fluid:sulfuric-acid")
        self.assertIn("sulfuric-acid", model["recipes"][0]["search"])
        self.assertIn("advanced-oil-processing", model["recipes"][0]["search"])
        self.assertIn("advanced-oil-processing", model["recipes"][0]["unlock_summary"])
        self.assertEqual(
            [unlock["name"] for unlock in model["recipes"][0]["recipe"]["unlock_technologies"]],
            ["oil-processing", "advanced-oil-processing"],
        )

    def test_partial_catalog_and_disabled_state_are_explicit(self):
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Recipe catalog pages are not fully assembled",
            "catalog_status": {
                "status": "ok",
                "page": 2,
                "total_pages": 4,
                "total_count": 60,
            },
            "capabilities": {
                "game_version": "2.0.77",
                "force": "player",
                "surface": "nauvis",
                "tick": 901,
                "recipes": [{
                    "name": "locked-recipe",
                    "enabled": False,
                    "hidden": False,
                    "simple": False,
                    "category": "crafting",
                    "crafting_time": 1,
                    "ingredients": [],
                    "products": [{"name": "locked-item", "type": "item", "amount": 1}],
                }],
                "research": [],
            },
        })

        self.assertIn("Partial catalog page 2 of 4", model["metadata"])
        self.assertEqual(model["recipes"][0]["availability"], "Disabled")
        self.assertIn("Planning disabled", model["status"])

    def test_missing_capabilities_are_not_rendered_as_a_catalog(self):
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Version/research/recipe catalog unavailable",
            "capabilities": None,
        })

        self.assertEqual(model["recipes"], [])
        self.assertEqual(model["research"], [])
        self.assertIn("unavailable", model["status"].lower())

    def test_assembled_pages_do_not_hide_truncated_snapshot(self):
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Recipe catalog empty/truncated: planning disabled",
            "catalog_status": {"status": "assembled"},
            "capabilities": {
                "game_version": "2.0.77",
                "force": "player",
                "surface": "nauvis",
                "tick": 902,
                "truncated": True,
                "recipes": [],
                "research": [],
                "enabled_content": [],
            },
        })

        self.assertIn("snapshot data is truncated", model["metadata"])


if __name__ == "__main__":
    unittest.main()
