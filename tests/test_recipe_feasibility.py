"""Recipe feasibility over an observed Factorio 2.1.23 catalog.

The model must separate "exists" from "unlocked" from "usable", and it must
report an unverifiable requirement as unknown rather than as satisfied or
impossible.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from recipe_feasibility import (
    STATUS_AVAILABLE,
    STATUS_LOCKED,
    STATUS_UNAVAILABLE,
    STATUS_UNKNOWN,
    assess_recipe,
    assess_recipes,
    usable_recipe_names,
)


def recipe(name="gear", *, enabled=True, hidden=False, unlocks=None,
           categories=None, category="crafting"):
    row = {
        "name": name,
        "enabled": enabled,
        "hidden": hidden,
        "simple": True,
        "category": category,
        "crafting_time": 0.5,
        "ingredients": [],
        "products": [{"name": name, "type": "item", "amount": 1}],
    }
    if unlocks is not None:
        row["unlock_technologies"] = unlocks
    if categories is not None:
        row["categories"] = categories
    return row


def unlock(name, *, researched=False, enabled=True):
    return {"name": name, "researched": researched, "enabled": enabled}


class AvailabilityTests(unittest.TestCase):
    def test_a_recipe_without_an_unlock_is_available(self):
        result = assess_recipe(recipe(), {"automation"})
        self.assertEqual(result.status, STATUS_AVAILABLE)
        self.assertTrue(result.is_usable)

    def test_a_disabled_recipe_is_unavailable(self):
        result = assess_recipe(recipe(enabled=False), {"automation"})
        self.assertEqual(result.status, STATUS_UNAVAILABLE)
        self.assertFalse(result.is_usable)

    def test_a_hidden_recipe_is_unavailable(self):
        result = assess_recipe(recipe(hidden=True), {"automation"})
        self.assertEqual(result.status, STATUS_UNAVAILABLE)
        self.assertFalse(result.is_usable)


class ResearchGateTests(unittest.TestCase):
    def test_an_unresearched_unlock_is_locked(self):
        """An unresearched technology must not be treated as researched."""
        result = assess_recipe(
            recipe(unlocks=[unlock("advanced-processing")]),
            {"automation"},
        )
        self.assertEqual(result.status, STATUS_LOCKED)
        self.assertFalse(result.is_usable)
        self.assertIn("advanced-processing", result.blocked_by)

    def test_a_researched_unlock_is_available(self):
        result = assess_recipe(
            recipe(unlocks=[unlock("advanced-processing", researched=True)]),
            {"automation"},
        )
        self.assertEqual(result.status, STATUS_AVAILABLE)
        self.assertTrue(result.is_usable)

    def test_a_disabled_unlock_technology_is_locked(self):
        result = assess_recipe(
            recipe(unlocks=[unlock("advanced-processing", researched=True,
                                   enabled=False)]),
            {"automation"},
        )
        self.assertEqual(result.status, STATUS_LOCKED)
        self.assertIn("advanced-processing", result.blocked_by)

    def test_one_missing_unlock_locks_the_whole_recipe(self):
        result = assess_recipe(
            recipe(unlocks=[
                unlock("a", researched=True),
                unlock("b", researched=False),
            ]),
            {"automation"},
        )
        self.assertEqual(result.status, STATUS_LOCKED)
        self.assertEqual(result.blocked_by, ("b",))

    def test_an_unknown_research_set_is_reported_as_unknown(self):
        """The unlock state cannot be established without the research set."""
        result = assess_recipe(
            recipe(unlocks=[unlock("advanced-processing")]),
            None,
        )
        self.assertEqual(result.status, STATUS_UNKNOWN)
        self.assertFalse(result.is_usable)
        self.assertTrue(
            any("unknown" in reason for reason in result.reasons)
        )


class MachineAvailabilityTests(unittest.TestCase):
    def test_an_available_recipe_reports_the_machine_as_unverified(self):
        """The catalog carries no machine prototypes, so it is unknown."""
        result = assess_recipe(recipe(), {"automation"})
        self.assertEqual(result.status, STATUS_AVAILABLE)
        self.assertTrue(
            any("crafting machine" in reason for reason in result.reasons)
        )


class CategoryTests(unittest.TestCase):
    def test_the_categories_are_reported(self):
        result = assess_recipe(
            recipe(categories=["chemistry", "crafting"]), {"automation"}
        )
        self.assertEqual(result.categories, ("chemistry", "crafting"))

    def test_the_primary_category_is_used_when_no_list_is_observed(self):
        result = assess_recipe(recipe(category="chemistry"), {"automation"})
        self.assertEqual(result.categories, ("chemistry",))


class CollectionTests(unittest.TestCase):
    def test_every_recipe_is_assessed(self):
        recipes = [
            recipe("a"),
            recipe("b", enabled=False),
            recipe("c", unlocks=[unlock("tech")]),
        ]
        results = assess_recipes(recipes, {"automation"})
        self.assertEqual(len(results), 3)
        self.assertEqual(results["a"].status, STATUS_AVAILABLE)
        self.assertEqual(results["b"].status, STATUS_UNAVAILABLE)
        self.assertEqual(results["c"].status, STATUS_LOCKED)

    def test_only_usable_recipes_are_returned(self):
        recipes = [
            recipe("a"),
            recipe("b", enabled=False),
            recipe("c", unlocks=[unlock("tech")]),
        ]
        self.assertEqual(usable_recipe_names(recipes, {"automation"}), {"a"})

    def test_a_locked_recipe_is_not_usable(self):
        recipes = [recipe("a", unlocks=[unlock("tech")])]
        self.assertEqual(usable_recipe_names(recipes, {"automation"}), set())

    def test_the_serialisation_keeps_the_status_and_reasons(self):
        data = assess_recipe(
            recipe(unlocks=[unlock("tech")]), {"automation"}
        ).as_dict()
        self.assertEqual(data["status"], STATUS_LOCKED)
        self.assertFalse(data["is_usable"])
        self.assertIn("tech", data["blocked_by"])
        self.assertTrue(data["reasons"])


if __name__ == "__main__":
    unittest.main()
