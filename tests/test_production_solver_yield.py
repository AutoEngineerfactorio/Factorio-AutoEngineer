"""Regression tests for the yield-aware production target in the solver.

These tests pin the behaviour that the effective-yield model must have inside
``agent/production_solver.py``:

* a bounded output never becomes a single false number;
* a probabilistic output is not treated as guaranteed;
* the craft rate uses the machine's crafting speed;
* the machine count follows from the requested rate;
* an alternative production path is reported;
* an unestablished machine speed is reported as unsupported, not assumed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.production_solver import (  # noqa: E402
    build_observed_recipe,
    compute_target_production,
)


def _recipe(name, products, crafting_time=1.0, ingredients=None):
    return {
        "name": name,
        "crafting_time": crafting_time,
        "products": products,
        "ingredients": ingredients or [],
    }


def _item(name, amount, **extra):
    part = {"name": name, "type": "item", "amount": amount}
    part.update(extra)
    return part


class BuildObservedRecipeTests(unittest.TestCase):
    def test_a_fixed_product_gives_a_guaranteed_output(self):
        observed = build_observed_recipe(
            _recipe("plate", [_item("iron-plate", 1)]), "item", "iron-plate"
        )
        self.assertEqual(observed.output_per_craft, 1.0)
        self.assertTrue(observed.output_deterministic)
        self.assertFalse(observed.yield_is_uncertain)

    def test_a_ranged_product_has_no_guaranteed_output(self):
        observed = build_observed_recipe(
            _recipe(
                "ore",
                [_item("iron-ore", 1, amount_min=1, amount_max=3)],
            ),
            "item",
            "iron-ore",
        )
        self.assertIsNone(observed.output_per_craft)
        self.assertEqual(observed.output_minimum, 1.0)
        self.assertEqual(observed.output_maximum, 3.0)
        self.assertIsNone(observed.output_expected)
        self.assertTrue(observed.yield_is_uncertain)
        self.assertTrue(observed.output_reasons)

    def test_a_probabilistic_product_is_not_guaranteed(self):
        observed = build_observed_recipe(
            _recipe(
                "rare",
                [_item("rare-item", 1, independent_probability=0.25)],
            ),
            "item",
            "rare-item",
        )
        self.assertIsNone(observed.output_per_craft)
        self.assertEqual(observed.output_probability, 0.25)
        self.assertEqual(observed.output_minimum, 0.0)

    def test_a_byproduct_does_not_change_the_target_output(self):
        observed = build_observed_recipe(
            _recipe(
                "copper",
                [_item("copper-cable", 2), _item("iron-plate", 1)],
            ),
            "item",
            "copper-cable",
        )
        self.assertEqual(observed.output_per_craft, 2.0)

    def test_a_missing_crafting_time_is_rejected(self):
        with self.assertRaises(ValueError):
            build_observed_recipe(
                {"name": "x", "crafting_time": 0, "products": [_item("a", 1)]}
            )

    def test_a_missing_name_is_rejected(self):
        with self.assertRaises(ValueError):
            build_observed_recipe(
                {"name": "", "crafting_time": 1, "products": [_item("a", 1)]}
            )


class CraftRateTests(unittest.TestCase):
    def test_the_craft_rate_uses_the_machine_speed(self):
        observed = build_observed_recipe(
            _recipe("plate", [_item("iron-plate", 1)], crafting_time=2.0),
            "item",
            "iron-plate",
            machine_speed=2.0,
        )
        self.assertEqual(observed.crafts_per_second(), 1.0)
        self.assertEqual(observed.units_per_second(), 1.0)

    def test_without_a_machine_speed_the_craft_rate_is_not_asserted(self):
        observed = build_observed_recipe(
            _recipe("plate", [_item("iron-plate", 1)], crafting_time=2.0),
            "item",
            "iron-plate",
        )
        self.assertIsNone(observed.crafts_per_second())
        self.assertIsNone(observed.units_per_second())


class ComputeTargetProductionTests(unittest.TestCase):
    def test_a_per_second_request_reports_the_rate_and_machine_count(self):
        result = compute_target_production(
            [_recipe("plate", [_item("iron-plate", 1)], crafting_time=2.0)],
            "item",
            "iron-plate",
            per_second=2.0,
            machine_speed=1.0,
            machine_name="assembling-machine-1",
            machine_energy_kw=90.0,
        )
        self.assertEqual(result.status, "estimated")
        self.assertEqual(result.requested_per_second, 2.0)
        self.assertEqual(result.requested_per_minute, 120.0)
        self.assertEqual(result.achievable_per_second, 0.5)
        self.assertEqual(result.achievable_per_minute, 30.0)
        self.assertEqual(result.machine_count, 4.0)
        self.assertEqual(result.machine_name, "assembling-machine-1")
        self.assertEqual(result.power_kw, 360.0)
        self.assertEqual(result.recipe, "plate")

    def test_a_per_minute_request_is_converted(self):
        result = compute_target_production(
            [_recipe("plate", [_item("iron-plate", 1)], crafting_time=1.0)],
            "item",
            "iron-plate",
            per_minute=60.0,
            machine_speed=1.0,
        )
        self.assertEqual(result.requested_per_second, 1.0)
        self.assertEqual(result.requested_per_minute, 60.0)
        self.assertEqual(result.achievable_per_second, 1.0)

    def test_both_rate_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production([], "item", "a", per_second=1.0, per_minute=1.0)

    def test_no_rate_argument_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production([], "item", "a")

    def test_a_non_positive_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production([], "item", "a", per_second=0.0)

    def test_an_uncertain_yield_does_not_produce_a_machine_count(self):
        result = compute_target_production(
            [
                _recipe(
                    "ore",
                    [_item("iron-ore", 1, amount_min=1, amount_max=3)],
                    crafting_time=1.0,
                )
            ],
            "item",
            "iron-ore",
            per_second=1.0,
            machine_speed=1.0,
        )
        self.assertEqual(result.status, "unsupported")
        self.assertIsNone(result.machine_count)
        self.assertIsNone(result.achievable_per_second)
        self.assertEqual(result.output_minimum, 1.0)
        self.assertEqual(result.output_maximum, 3.0)
        self.assertTrue(result.unsupported)

    def test_a_missing_machine_speed_is_reported_as_unsupported(self):
        result = compute_target_production(
            [_recipe("plate", [_item("iron-plate", 1)], crafting_time=1.0)],
            "item",
            "iron-plate",
            per_second=1.0,
        )
        self.assertEqual(result.status, "unsupported")
        self.assertTrue(
            any("machine" in reason for reason in result.unsupported)
        )

    def test_an_alternative_production_path_is_reported(self):
        result = compute_target_production(
            [
                _recipe("fast", [_item("iron-plate", 1)], crafting_time=0.5),
                _recipe("slow", [_item("iron-plate", 1)], crafting_time=2.0),
            ],
            "item",
            "iron-plate",
            per_second=1.0,
            machine_speed=1.0,
        )
        self.assertEqual(result.recipe, "fast")
        self.assertEqual(len(result.alternatives), 1)
        self.assertEqual(result.alternatives[0]["recipe"], "slow")
        self.assertEqual(result.alternatives[0]["units_per_second"], 0.5)
        self.assertEqual(result.alternatives[0]["machine_count"], 2.0)

    def test_no_candidate_recipe_is_unavailable(self):
        result = compute_target_production(
            [], "item", "missing", per_second=1.0, machine_speed=1.0
        )
        self.assertEqual(result.status, "unavailable")
        self.assertTrue(result.unsupported)

    def test_a_zero_machine_speed_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production([], "item", "a", per_second=1.0, machine_speed=0.0)

    def test_a_negative_machine_speed_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production([], "item", "a", per_second=1.0, machine_speed=-1.0)

    def test_a_negative_machine_power_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production(
                [], "item", "a", per_second=1.0, machine_speed=1.0, machine_energy_kw=-5.0
            )

    def test_a_boolean_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production([], "item", "a", per_second=True)

    def test_an_infinite_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_target_production([], "item", "a", per_second=float("inf"))

    def test_a_boolean_crafting_time_is_rejected(self):
        with self.assertRaises(ValueError):
            build_observed_recipe(
                {"name": "x", "crafting_time": True, "products": [_item("a", 1)]}
            )

    def test_the_result_is_json_safe(self):
        result = compute_target_production(
            [_recipe("plate", [_item("iron-plate", 1)], crafting_time=1.0)],
            "item",
            "iron-plate",
            per_second=1.0,
            machine_speed=1.0,
        )
        data = result.as_dict()
        self.assertIsInstance(data["requested_per_second"], float)
        self.assertIsInstance(data["alternatives"], list)
        self.assertIsInstance(data["notes"], list)
        self.assertNotIn("object", str(data))


class ModuleContractTests(unittest.TestCase):
    def test_the_module_docstring_does_not_claim_the_observed_path_is_missing(self):
        import agent.production_solver as solver

        doc = (solver.__doc__ or "").casefold()
        self.assertNotIn("r06 and live-game acceptance remain incomplete", doc)
        self.assertIn("observed-catalog path", doc)

    def test_the_numeric_helper_rejects_a_boolean(self):
        from agent.production_solver import _finite_number

        self.assertIsNone(_finite_number(True))
        self.assertIsNone(_finite_number(False))

    def test_the_numeric_helper_rejects_a_non_finite_value(self):
        from agent.production_solver import _finite_number

        self.assertIsNone(_finite_number(float("nan")))
        self.assertIsNone(_finite_number(float("inf")))
        self.assertIsNone(_finite_number(None))
        self.assertIsNone(_finite_number("3"))

    def test_the_numeric_helper_accepts_a_finite_number(self):
        from agent.production_solver import _finite_number

        self.assertEqual(_finite_number(3), 3.0)
        self.assertEqual(_finite_number(2.5), 2.5)
        self.assertEqual(_finite_number(0), 0.0)


if __name__ == "__main__":
    unittest.main()
