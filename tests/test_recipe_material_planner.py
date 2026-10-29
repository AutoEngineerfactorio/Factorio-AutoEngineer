"""Read-only recipe material planning over complete, qualified catalogs."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from read_only_planning import view_intelligence
from recipe_material_planner import (
    format_target_production,
    plan_product_materials,
    plan_target_production,
)


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
        "game_version": "2.1.23",
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
        self.assertEqual(plan["source"], {
            "game_version": "2.1.23",
            "fingerprint": "poly31x131-v1:0123456789-9876543210",
            "force": "player", "surface": "nauvis", "tick": 120,
            "enabled_content": ["base"], "observed_research": ["automation"],
        })
        self.assertEqual(plan["throughput_status"], "not-computed")
        self.assertFalse(plan["physical_buildability_verified"])
        self.assertEqual(plan["uncertainty"], plan["unresolved"])

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
        self.assertEqual(plan["coproduct_credit_policy"],
                         "reported-only; no requirement credits applied")
        detail = plan["selected_recipe_details"][0]
        self.assertEqual(detail["crafting_time_seconds"], 1)
        self.assertEqual(detail["ingredients_per_craft"], [part("ore", 1)])
        self.assertEqual(detail["products_per_craft"],
                         [part("plate", 1), part("slag", 0.5)])
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
        self.assertEqual(plan["recipe_ambiguities"], plan["unresolved"])
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
        self.assertEqual(plan["unsupported_mechanics"],
                         [plan["unresolved"][0]["reason"]])

    def test_disabled_recipe_is_not_reported_as_available_or_nonproducible(self):
        observed = intelligence([
            recipe("locked-gear", [part("plate", 2)], [part("gear", 1)], enabled=False),
        ])

        plan = plan_product_materials(observed, "item", "gear", 1)

        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["selected_recipes"], [])
        self.assertIn("no currently enabled recipe", plan["unresolved"][0]["reason"])
        self.assertIn("locked-gear", plan["unresolved"][0]["candidates"])
        self.assertEqual(plan["research_unlock_limitations"], plan["unresolved"])

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


class EffectiveYieldPlannerTests(unittest.TestCase):
    """The planner must use the effective yield, not the nominal amount.

    A ranged or probabilistic product has no single guaranteed amount, so
    the planner must report the bounds and the uncertainty instead of
    computing a falsely precise batch count.
    """

    def test_a_ranged_product_reports_its_bounds_not_a_single_amount(self):
        observed = intelligence([
            recipe("mining", [part("rock", 1)], [
                {**part("ore", 1), "amount_min": 1, "amount_max": 3},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "ore", 3)

        detail = plan["selected_recipe_details"][0]
        self.assertEqual(detail["target_yield"]["minimum"], 1)
        self.assertEqual(detail["target_yield"]["maximum"], 3)
        self.assertIsNone(detail["target_yield"]["expected"])
        self.assertTrue(detail["target_yield"]["is_uncertain"])

    def test_a_ranged_product_does_not_produce_a_confident_batch_count(self):
        """The batch count must not pretend the yield is known."""
        observed = intelligence([
            recipe("mining", [part("rock", 1)], [
                {**part("ore", 1), "amount_min": 1, "amount_max": 3},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "ore", 3)

        self.assertEqual(plan["status"], "partial")
        self.assertTrue(plan["uncertainty"])
        self.assertTrue(
            any("range" in row["reason"] for row in plan["unresolved"])
            or plan["selected_recipe_details"][0]["target_yield"]["is_uncertain"]
        )

    def test_a_probabilistic_product_reports_its_probability(self):
        observed = intelligence([
            recipe("lucky", [part("rock", 1)], [
                {**part("gem", 1), "independent_probability": 0.25},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "gem", 1)

        detail = plan["selected_recipe_details"][0]
        self.assertEqual(detail["target_yield"]["probability"], 0.25)
        self.assertIsNone(detail["target_yield"]["guaranteed"])

    def test_a_fixed_product_keeps_a_confident_batch_count(self):
        observed = intelligence([
            recipe("smelting", [part("ore", 1)], [part("plate", 1)]),
        ])

        plan = plan_product_materials(observed, "item", "plate", 2)

        self.assertEqual(plan["selected_recipes"], [
            {"recipe": "smelting", "batches": 2},
        ])
        detail = plan["selected_recipe_details"][0]
        self.assertEqual(detail["target_yield"]["guaranteed"], 1)
        self.assertFalse(detail["target_yield"]["is_uncertain"])

    def test_the_yield_of_every_product_is_reported(self):
        observed = intelligence([
            recipe("smelting", [part("ore", 1)], [
                part("plate", 1),
                {**part("slag", 0.5), "percent_spoiled": 0.5},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "plate", 1)

        detail = plan["selected_recipe_details"][0]
        self.assertEqual(len(detail["product_yields"]), 2)
        self.assertEqual(detail["product_yields"][0]["guaranteed"], 1)
        self.assertEqual(detail["product_yields"][1]["expected"], 0.25)

    def test_a_spoiled_coproduct_reports_its_uncertainty(self):
        observed = intelligence([
            recipe("smelting", [part("ore", 1)], [
                part("plate", 1),
                {**part("slag", 0.5), "percent_spoiled": 0.5},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "plate", 1)

        coproduct = plan["uncredited_coproducts"][0]
        self.assertEqual(coproduct["name"], "slag")
        yield_row = plan["coproduct_yields"]["smelting|item:slag"]
        self.assertTrue(yield_row["is_uncertain"])
        # Spoilage reduces the amount by a known factor, so the expectation
        # is known even though the yield is not guaranteed.
        self.assertEqual(yield_row["expected"], 0.25)
        self.assertIsNone(yield_row["guaranteed"])

    def test_a_recipe_with_an_unsupported_mechanic_lists_it(self):
        observed = intelligence([
            recipe("ranged", [part("rock", 1)], [
                {**part("ore", 1), "amount_min": 1, "amount_max": 3},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "ore", 1)

        self.assertTrue(plan["unsupported_mechanics"])
        self.assertTrue(
            any("range" in reason or "expected" in reason
                for reason in plan["unsupported_mechanics"])
        )


class ResearchGatePlannerTests(unittest.TestCase):
    """A recipe locked behind an unresearched technology is not available.

    The planner must not treat an unresearched unlock technology as
    researched, and it must say which technology blocks the recipe.
    """

    @staticmethod
    def _recipe_with_unlock(name, unlocks):
        row = recipe(name, [part("ore", 1)], [part(name, 1)])
        row["unlock_technologies"] = unlocks
        return row

    def test_a_research_locked_recipe_is_not_planned(self):
        observed = intelligence([
            self._recipe_with_unlock("gear", [
                {"name": "advanced-processing", "researched": False, "enabled": True},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "gear", 1)

        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["selected_recipes"], [])
        self.assertTrue(plan["unresolved"])
        self.assertIn("advanced-processing", plan["unresolved"][0]["reason"])

    def test_a_researched_unlock_is_planned(self):
        observed = intelligence([
            self._recipe_with_unlock("gear", [
                {"name": "advanced-processing", "researched": True, "enabled": True},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "gear", 1)

        self.assertEqual(plan["selected_recipes"], [
            {"recipe": "gear", "batches": 1},
        ])

    def test_a_disabled_unlock_technology_blocks_the_recipe(self):
        observed = intelligence([
            self._recipe_with_unlock("gear", [
                {"name": "advanced-processing", "researched": True, "enabled": False},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "gear", 1)

        self.assertEqual(plan["selected_recipes"], [])
        self.assertTrue(plan["unresolved"])

    def test_the_research_gate_is_reported_in_the_plan(self):
        observed = intelligence([
            self._recipe_with_unlock("gear", [
                {"name": "advanced-processing", "researched": False, "enabled": True},
            ]),
        ])

        plan = plan_product_materials(observed, "item", "gear", 1)

        self.assertTrue(plan["research_lock_limitations"])
        self.assertIn(
            "advanced-processing",
            plan["research_lock_limitations"][0]["reason"],
        )

    def test_the_feasibility_of_each_recipe_is_reported(self):
        observed = intelligence([
            self._recipe_with_unlock("gear", [
                {"name": "advanced-processing", "researched": False, "enabled": True},
            ]),
            recipe("plate", [part("ore", 1)], [part("plate", 1)]),
        ])

        plan = plan_product_materials(observed, "item", "plate", 1)

        statuses = {
            row["recipe"]: row["status"]
            for row in plan["recipe_feasibility"]
        }
        self.assertEqual(statuses["gear"], "locked")
        self.assertEqual(statuses["plate"], "available")


class TargetProductionPlannerTests(unittest.TestCase):
    """The production target is reported in items/sec and items/min."""

    def _recipe_with_unlock(self, name, ingredients, products, unlocks=None,
                            crafting_time=1.0):
        row = recipe(name, ingredients, products)
        row["crafting_time"] = crafting_time
        if unlocks is not None:
            row["unlock_technologies"] = unlocks
        return row

    def test_a_per_second_target_reports_the_rate_and_machine_count(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "plate", [part("ore", 1)], [part("plate", 1)], crafting_time=2.0),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_second=2.0,
            machine_speed=1.0, machine_name="assembling-machine-1",
            machine_energy_kw=90.0,
        )

        self.assertEqual(plan["status"], "estimated")
        self.assertEqual(plan["requested_per_second"], 2.0)
        self.assertEqual(plan["requested_per_minute"], 120.0)
        self.assertEqual(plan["achievable_per_second"], 0.5)
        self.assertEqual(plan["achievable_per_minute"], 30.0)
        self.assertEqual(plan["machine_count"], 4.0)
        self.assertEqual(plan["machine_name"], "assembling-machine-1")
        self.assertEqual(plan["power_kw"], 360.0)
        self.assertEqual(plan["recipe"], "plate")
        self.assertFalse(plan["physical_buildability_verified"])

    def test_a_per_minute_target_is_converted_to_items_per_second(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "plate", [part("ore", 1)], [part("plate", 1)], crafting_time=1.0),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_minute=120.0, machine_speed=1.0,
        )

        self.assertEqual(plan["requested_per_second"], 2.0)
        self.assertEqual(plan["requested_per_minute"], 120.0)
        self.assertEqual(plan["achievable_per_second"], 1.0)

    def test_without_a_machine_speed_the_machine_count_is_not_asserted(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "plate", [part("ore", 1)], [part("plate", 1)], crafting_time=1.0),
        ])

        plan = plan_target_production(observed, "item", "plate", per_second=1.0)

        self.assertEqual(plan["status"], "unsupported")
        self.assertIsNone(plan["machine_count"])
        self.assertTrue(plan["unsupported"])

    def test_an_alternative_production_path_is_reported(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "fast", [part("ore", 1)], [part("plate", 1)], crafting_time=0.5),
            self._recipe_with_unlock(
                "slow", [part("ore", 1)], [part("plate", 1)], crafting_time=2.0),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_second=1.0, machine_speed=1.0,
        )

        self.assertEqual(plan["recipe"], "fast")
        self.assertEqual(len(plan["alternatives"]), 1)
        self.assertEqual(plan["alternatives"][0]["recipe"], "slow")
        self.assertEqual(plan["alternatives"][0]["units_per_second"], 0.5)
        self.assertEqual(plan["alternatives"][0]["machine_count"], 2.0)

    def test_a_research_locked_path_is_not_counted_as_usable(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "plate", [part("ore", 1)], [part("plate", 1)], crafting_time=1.0),
            self._recipe_with_unlock(
                "locked-plate", [part("ore", 1)], [part("plate", 1)],
                unlocks=[{
                    "name": "advanced-processing",
                    "researched": False,
                    "enabled": True,
                }],
            ),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_second=1.0, machine_speed=1.0,
        )

        self.assertEqual(plan["recipe"], "plate")
        self.assertEqual(plan["alternatives"], [])
        self.assertEqual(plan["locked_alternative_paths"], ["locked-plate"])
        self.assertTrue(
            any("locked" in reason for reason in plan["unsupported"])
        )

    def test_a_bounded_output_is_not_expanded_into_a_machine_count(self):
        row = recipe("ore-mining", [part("rock", 1)], [part("ore", 1)])
        row["products"] = [
            {"name": "ore", "amount": 1, "type": "item",
             "amount_min": 1, "amount_max": 3},
        ]
        observed = intelligence([row])

        plan = plan_target_production(
            observed, "item", "ore", per_second=1.0, machine_speed=1.0,
        )

        self.assertEqual(plan["status"], "unsupported")
        self.assertIsNone(plan["machine_count"])
        self.assertEqual(plan["output_minimum"], 1.0)
        self.assertEqual(plan["output_maximum"], 3.0)

    def test_the_formatted_plan_names_what_is_not_established(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "plate", [part("ore", 1)], [part("plate", 1)], crafting_time=1.0),
        ])

        plan = plan_target_production(observed, "item", "plate", per_second=1.0)
        text = format_target_production(plan)

        self.assertIn("Production target: unsupported", text)
        self.assertIn("Requested: 1 /s (60 /min)", text)
        self.assertIn("Not established:", text)

    def test_a_target_without_an_observed_recipe_is_unavailable(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "plate", [part("ore", 1)], [part("plate", 1)], crafting_time=1.0),
        ])

        plan = plan_target_production(
            observed, "item", "missing", per_second=1.0, machine_speed=1.0,
        )

        self.assertEqual(plan["status"], "unavailable")
        self.assertTrue(plan["unsupported"])

    def test_a_target_with_only_locked_recipes_is_unavailable(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "locked-plate", [part("ore", 1)], [part("plate", 1)],
                unlocks=[{
                    "name": "advanced-processing",
                    "researched": False,
                    "enabled": True,
                }],
            ),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_second=1.0, machine_speed=1.0,
        )

        self.assertEqual(plan["status"], "unavailable")
        self.assertEqual(plan["locked_alternative_paths"], ["locked-plate"])
        self.assertTrue(
            any("locked" in reason for reason in plan["unsupported"])
        )

    def test_an_unqualified_catalog_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_target_production({}, "item", "plate", per_second=1.0)

    def test_both_rate_arguments_are_rejected(self):
        observed = intelligence([
            self._recipe_with_unlock(
                "plate", [part("ore", 1)], [part("plate", 1)], crafting_time=1.0),
        ])
        with self.assertRaises(ValueError):
            plan_target_production(
                observed, "item", "plate", per_second=1.0, per_minute=1.0,
            )


if __name__ == "__main__":
    unittest.main()
