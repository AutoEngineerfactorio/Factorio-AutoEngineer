"""Read-only recipe material planning over complete, qualified catalogs."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from read_only_planning import view_intelligence
from recipe_material_planner import plan_product_materials


def recipe(name, ingredients, products, *, enabled=True, hidden=False):
    return {
        "name": name,
        "enabled": enabled,
        "hidden": hidden,
        "simple": enabled and not hidden and len(products) == 1
        and all(part["type"] == "item" for part in ingredients + products),
        "category": "crafting",
        "crafting_time": 1,
        "ingredients": ingredients,
        "products": products,
    }


def part(name, amount, material_type="item"):
    return {"name": name, "amount": amount, "type": material_type}


def intelligence(recipes, *, truncated=False, enabled_content=None):
    raw = {
        "schema": 1,
        "tick": 120,
        "surface": "nauvis",
        "game_version": "2.0.77",
        "force": "player",
        "research": ["automation"],
        "enabled_content": enabled_content or ["base"],
        "truncated": truncated,
        "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
        "recipes": recipes,
    }
    return view_intelligence({
        "status": "ok",
        "tick": 120,
        "surface": "nauvis",
        "position": {"x": 0, "y": 0},
        "inventory": [],
        "inventory_available": True,
        "truncated": False,
        "capabilities": raw,
        "catalog_status": {"status": "assembled"},
    }, received_at=100)


class RecipeMaterialPlannerTests(unittest.TestCase):
    def test_recursively_aggregates_shared_item_requirements(self):
        observed = intelligence([
            recipe("module", [part("gear", 2), part("circuit", 2)], [part("module", 1)]),
            recipe("gear", [part("iron-plate", 1)], [part("gear", 1)]),
            recipe("circuit", [part("iron-plate", 1)], [part("circuit", 1)]),
            recipe("iron-plate", [part("iron-ore", 1)], [part("iron-plate", 1)]),
        ])

        plan = plan_product_materials(observed, "item", "module", 1)

        self.assertEqual(plan["status"], "partial")
        self.assertEqual(
            {row["recipe"]: row["batches"] for row in plan["selected_recipes"]},
            {"circuit": 2, "gear": 2, "iron-plate": 4, "module": 1},
        )
        ore = next(row for row in plan["unresolved"] if row["name"] == "iron-ore")
        self.assertEqual(ore["amount"], 4)
        self.assertIn("external supply/buildability is unknown", ore["reason"])

    def test_fluid_target_and_fluid_inputs_keep_distinct_units(self):
        observed = intelligence([
            recipe(
                "sulfuric-acid",
                [part("water", 3, "fluid"), part("iron-plate", 1)],
                [part("sulfuric-acid", 2, "fluid")],
            ),
        ])

        plan = plan_product_materials(observed, "fluid", "sulfuric-acid", 4)

        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["selected_recipes"], [
            {"recipe": "sulfuric-acid", "batches": 2},
        ])
        unresolved = {(row["type"], row["name"]): row["amount"] for row in plan["unresolved"]}
        self.assertEqual(unresolved[("fluid", "water")], 6)
        self.assertEqual(unresolved[("item", "iron-plate")], 2)

    def test_multi_output_recipe_reports_uncredited_coproducts(self):
        observed = intelligence([
            recipe(
                "smelting",
                [part("ore", 1)],
                [part("plate", 1), part("slag", 0.5)],
            ),
        ])

        plan = plan_product_materials(observed, "item", "plate", 2)

        self.assertEqual(plan["selected_recipes"], [
            {"recipe": "smelting", "batches": 2},
        ])
        self.assertEqual(plan["uncredited_coproducts"], [{
            "recipe": "smelting",
            "type": "item",
            "name": "slag",
            "amount": 1,
        }])
        self.assertTrue(any("not credited" in note for note in plan["notes"]))

    def test_ambiguous_recipe_requires_user_choice(self):
        observed = intelligence([
            recipe("gear-basic", [part("plate", 2)], [part("gear", 1)]),
            recipe("gear-alternate", [part("scrap", 1)], [part("gear", 1)]),
        ])

        plan = plan_product_materials(observed, "item", "gear", 3)
        selected = plan_product_materials(
            observed, "item", "gear", 3, choices={"item:gear": "gear-alternate"}
        )

        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["unresolved"][0]["candidates"], [
            "gear-alternate", "gear-basic",
        ])
        self.assertEqual(selected["selected_recipes"], [
            {"recipe": "gear-alternate", "batches": 3},
        ])
        self.assertEqual(selected["unresolved"][0]["name"], "scrap")

    def test_cycles_are_unsupported_and_never_treated_as_free_material(self):
        observed = intelligence([
            recipe("a", [part("b", 1)], [part("a", 1)]),
            recipe("b", [part("a", 1)], [part("b", 1)]),
        ])

        plan = plan_product_materials(observed, "item", "a", 1)

        self.assertEqual(plan["status"], "unsupported")
        self.assertIn("recipe cycle:", plan["unresolved"][0]["reason"])

    def test_disabled_recipe_is_not_reported_as_available_or_nonproducible(self):
        observed = intelligence([
            recipe("locked-gear", [part("plate", 2)], [part("gear", 1)], enabled=False),
        ])

        plan = plan_product_materials(observed, "item", "gear", 1)

        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["selected_recipes"], [])
        self.assertIn("no currently enabled recipe", plan["unresolved"][0]["reason"])
        self.assertIn("locked-gear", plan["unresolved"][0]["candidates"])

    def test_planning_rejects_incomplete_or_unqualified_catalogs(self):
        incomplete = intelligence([
            recipe("gear", [part("plate", 2)], [part("gear", 1)]),
        ], truncated=True)
        unqualified = intelligence([
            recipe("gear", [part("plate", 2)], [part("gear", 1)]),
        ], enabled_content=["base", "space-age"])

        for observed in (incomplete, unqualified):
            with self.subTest(observed=observed["reason"]), self.assertRaises(ValueError):
                plan_product_materials(observed, "item", "gear")

    def test_invalid_target_and_unbounded_recipe_choices_are_rejected(self):
        observed = intelligence([
            recipe("gear", [part("plate", 2)], [part("gear", 1)]),
        ])
        for material_type, name, amount in (
            ("energy", "gear", 1),
            ("item", "gear", 0),
            ("item", "gear", float("inf")),
            ("item", "", 1),
        ):
            with self.subTest(material_type=material_type, name=name, amount=amount):
                with self.assertRaises(ValueError):
                    plan_product_materials(observed, material_type, name, amount)
        with self.assertRaises(ValueError):
            plan_product_materials(
                observed, "item", "gear",
                choices={"item:gear": "not-an-observed-recipe"},
            )


if __name__ == "__main__":
    unittest.main()
