"""Offline regression tests for the R10-B AI Helper supply integration.

The AI Helper must plan against the **observed** factory, not only against
the theoretical recipe graph. The tests pin:

* the available items come from the observed inventories and the logistic
  networks;
* an item that was **not observed** is unknown, never zero;
* the observed recipes and the observed machine count are reported;
* the theoretical requirement and the observed supply stay **separate**;
* a planner without the observation still works.

No game process, no save, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from observed_supply import (  # noqa: E402
    observed_supply,
    supply_evidence,
)
from read_only_planning import view_intelligence  # noqa: E402


def machine_row(name: str = "assembling-machine-1",
                recipe: str | None = "iron-gear-wheel",
                items: list | None = None) -> dict:
    """Return one observed machine row."""
    return {
        "name": name,
        "type": "assembling-machine",
        "surface": "nauvis",
        "quality": "normal",
        "x": 10, "y": -20,
        "active": True,
        "recipe": recipe,
        "inventories": [{
            "category": "ingredient",
            "identifier": "chest",
            "capacity": 4,
            "items": items if items is not None else [
                {"name": "iron-plate", "count": 100, "quality": "normal"},
            ],
            "empty": not items,
            "truncated": False,
        }],
        "fluids": [],
    }


def network_row(network_id: int = 1, items: list | None = None) -> dict:
    """Return one observed logistic network row."""
    return {
        "network_id": network_id,
        "surface": "nauvis",
        "force": "player",
        "custom_name": "main",
        "available_logistic_robots": 120,
        "all_logistic_robots": 200,
        "available_construction_robots": 30,
        "all_construction_robots": 60,
        "robot_limit": 250,
        "items": items if items is not None else [
            {"name": "copper-plate", "count": 2500, "quality": "normal"},
        ],
        "providers": ["provider-chest"],
        "requesters": [],
        "storages": [],
        "items_truncated": False,
    }


def inventory_frame(**sections) -> dict:
    """Return one ``autoengineer_inventory`` frame."""
    payload = {
        "status": "ok",
        "protocol": 1,
        "tick": 1234,
        "surface": "nauvis",
        "machine_inventories": {
            "available": True, "status": "ok",
            "page": 1, "page_size": 16, "total": 1, "page_count": 1,
            "matched": 1, "partial": False, "truncated": False,
            "snapshot": "1234:1",
            "rows": [machine_row()],
        },
        "logistics": {
            "available": True, "status": "ok",
            "page": 1, "page_size": 16, "total": 1, "page_count": 1,
            "snapshot": "1234:1",
            "rows": [network_row()],
        },
        "robots": {
            "available": True, "status": "ok", "networks": 1,
            "total_logistic_robots": 200, "available_logistic_robots": 120,
            "total_construction_robots": 60,
            "available_construction_robots": 30,
            "robot_limit": 250, "partial": False,
        },
        "transport": {
            "available": True, "status": "ok",
            "page": 1, "page_size": 16, "total": 0, "page_count": 1,
            "matched": 0, "rows": [],
        },
    }
    payload.update(sections)
    return payload


def view_frame(**overrides) -> dict:
    """Return one ``autoengineer_view`` frame."""
    payload = {
        "status": "ok",
        "protocol": 1,
        "tick": 1234,
        "x": 10, "y": -20,
        "surface": "nauvis",
        "position": {"x": 10, "y": -20},
        "inventory": [{"name": "iron-plate", "count": 3, "quality": "normal"}],
        "inventory_available": True,
        "truncated": False,
    }
    payload.update(overrides)
    return payload


class ObservedSupplyTests(unittest.TestCase):
    """The supply must come from the observation and nothing else."""

    def test_an_absent_observation_is_unavailable(self):
        supply = observed_supply(None)
        self.assertEqual(supply.state, "unavailable")
        self.assertFalse(supply.known)
        self.assertEqual(supply.available, ())

    def test_the_available_items_come_from_the_observation(self):
        supply = observed_supply(inventory_frame())
        self.assertTrue(supply.known)
        self.assertEqual(supply.available_count("iron-plate"), 100)
        self.assertEqual(supply.available_count("copper-plate"), 2500)

    def test_an_item_that_was_not_observed_is_unknown_not_zero(self):
        supply = observed_supply(inventory_frame())
        self.assertIsNone(supply.available_count("copper-ore"))
        self.assertIsNone(supply.is_observed_available("copper-ore"))

    def test_an_observed_item_with_a_zero_count_is_reported_as_zero(self):
        payload = inventory_frame()
        payload["machine_inventories"]["rows"] = [
            machine_row(items=[{"name": "iron-plate", "count": 0,
                                "quality": "normal"}]),
        ]
        supply = observed_supply(payload)
        self.assertEqual(supply.available_count("iron-plate"), 0)
        self.assertFalse(supply.is_observed_available("iron-plate"))

    def test_the_observed_recipes_are_reported(self):
        supply = observed_supply(inventory_frame())
        self.assertIn("iron-gear-wheel", supply.observed_recipes)
        self.assertEqual(supply.machine_count, 1)

    def test_a_machine_without_a_recipe_is_still_counted(self):
        payload = inventory_frame()
        payload["machine_inventories"]["rows"] = [machine_row(recipe=None)]
        supply = observed_supply(payload)
        self.assertEqual(supply.machine_count, 1)
        self.assertEqual(supply.observed_recipes, ())

    def test_the_robot_capacity_is_reported(self):
        supply = observed_supply(inventory_frame())
        self.assertEqual(supply.total_logistic_robots, 200)
        self.assertEqual(supply.available_logistic_robots, 120)
        self.assertEqual(supply.total_construction_robots, 60)
        self.assertEqual(supply.available_construction_robots, 30)
        self.assertEqual(supply.robot_limit, 250)

    def test_the_availability_is_kept_separate_per_source(self):
        supply = observed_supply(inventory_frame())
        self.assertIn("network:1", supply.sources)
        self.assertIn("entity:assembling-machine-1", supply.sources)

    def test_the_supply_evidence_is_bounded_and_json_safe(self):
        evidence = supply_evidence(observed_supply(inventory_frame()))
        self.assertEqual(evidence["available_items"], 2)
        self.assertEqual(evidence["logistic_networks"], 1)
        self.assertEqual(evidence["observed_machines"], 1)
        self.assertIn("iron-gear-wheel", evidence["observed_recipes"])

    def test_the_supply_evidence_is_json_serialisable(self):
        import json
        json.dumps(supply_evidence(observed_supply(inventory_frame())))


class PlannerSupplyIntegrationTests(unittest.TestCase):
    """The AI Helper must consume the same observation the dashboard reads."""

    def test_the_planner_reports_the_observed_supply(self):
        result = view_intelligence(view_frame(),
                                   inventory_observation=inventory_frame())
        self.assertTrue(result["supply_observed"])
        supply = result["observed_supply"]
        self.assertIsNotNone(supply)
        names = {item["name"] for item in supply["available"]}
        self.assertIn("iron-plate", names)
        self.assertIn("copper-plate", names)

    def test_the_planner_without_the_observation_still_works(self):
        result = view_intelligence(view_frame())
        self.assertFalse(result["supply_observed"])
        self.assertIsNone(result["observed_supply"])

    def test_the_theoretical_catalog_and_the_observed_supply_stay_separate(self):
        result = view_intelligence(view_frame(),
                                   inventory_observation=inventory_frame())
        # The capabilities carry the theoretical recipe graph; the observed
        # supply is a separate key. The two are never merged.
        self.assertIn("capabilities", result)
        self.assertIn("observed_supply", result)
        self.assertNotIn("available_items", result.get("capabilities") or {})

    def test_the_planner_rejects_an_unusable_observation(self):
        """A frame that is not a mapping is ignored, not trusted."""
        result = view_intelligence(view_frame(),
                                   inventory_observation="not-a-frame")
        self.assertFalse(result["supply_observed"])

    def test_the_mechanics_ledger_carries_the_supply(self):
        result = view_intelligence(view_frame(),
                                   inventory_observation=inventory_frame())
        summary = result["mechanics"]
        # The inventory mechanic now carries evidence from both the player
        # inventory and the observed factory supply, so the observed
        # dimension covers it.
        self.assertGreaterEqual(summary["categories_with_evidence"], 2)
        self.assertGreaterEqual(summary["dimension_counts"]["observed"], 2)


if __name__ == "__main__":
    unittest.main()
