"""Boundary tests for the explicitly partial offline recipe-rate estimator."""
import math
import sys
import unittest
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from production_solver import ProductionSolver, create_machine, create_recipe


class RateEstimatorBoundaries(unittest.TestCase):
    def setUp(self):
        self.solver = ProductionSolver(profile_version="offline-fixture")
        self.solver.add_recipe(create_recipe(
            "gear", 5, 0.5, inputs=[{"prototype_id": "iron-plate", "count": 2}]
        ))

    def test_factorio_machine_crafting_speed_can_exceed_one(self):
        self.solver.add_machine(create_machine(
            "gear", "fast fixture machine", speed_multiplier=1.25
        ))
        plan = self.solver.compute_production_plan(
            "gear", 6.25, {"iron-plate": 100}, 100
        )
        self.assertAlmostEqual(plan.achievable_rate_gps, 6.25)
        self.assertAlmostEqual(plan.utilization_ideal, 1)
        self.assertEqual(plan.feasibility_status, "estimated")

    def test_unmodeled_input_free_recipe_is_only_a_partial_estimate(self):
        self.solver.add_recipe(create_recipe("free-item", 5, 0.5))
        plan = self.solver.compute_production_plan("free-item", 5, {}, 100)
        self.assertEqual(plan.feasibility_status, "partial")
        self.assertIn("unmodeled-source-throughput", plan.supply_limiting)

    def test_unimplemented_catalyst_and_byproduct_balance_is_explicit(self):
        self.solver.add_recipe(create_recipe(
            "complex-item", 1, 0.1, catalysts=["catalyst"],
            byproducts=[{"prototype_id": "scrap", "count": 1}],
            inputs=[{"prototype_id": "catalyst", "count": 1, "is_catalyst": True}],
        ))
        plan = self.solver.compute_production_plan(
            "complex-item", 1, {"catalyst": 0}, 100
        )
        self.assertEqual(plan.feasibility_status, "partial")
        self.assertIn("unverified-catalyst-inventory-or-return", plan.supply_limiting)
        self.assertIn("unsupported-byproduct-balance", plan.supply_limiting)
        self.assertNotIn("supply-catalyst", plan.supply_limiting)

    def test_nonfinite_or_negative_plan_inputs_are_rejected(self):
        invalid_targets = (-1, float("nan"), float("inf"), True)
        for target in invalid_targets:
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.solver.compute_production_plan("gear", target, {}, 100)
        for energy in (-1, float("nan"), float("inf"), True):
            with self.subTest(energy=energy), self.assertRaises(ValueError):
                self.solver.compute_production_plan("gear", 1, {}, energy)
        for supply in (
            {"iron-plate": -1},
            {"iron-plate": float("nan")},
            {"unused": float("inf")},
            {"iron-plate": True},
        ):
            with self.subTest(supply=supply), self.assertRaises(ValueError):
                # Supply maps intentionally include invalid values in this negative test.
                self.solver.compute_production_plan("gear", 1, cast(Any, supply), 100)

    def test_nonfinite_machine_and_recipe_data_are_rejected(self):
        with self.assertRaises(ValueError):
            self.solver.add_machine(create_machine(
                "gear", "bad machine", speed_multiplier=math.nan
            ))
        with self.assertRaises(ValueError):
            self.solver.add_machine(create_machine(
                "gear", "bad machine", productivity_bonus=-0.1
            ))
        with self.assertRaises(ValueError):
            self.solver.add_recipe(create_recipe("bad", math.inf, 1))
        with self.assertRaises(ValueError):
            self.solver.add_recipe(create_recipe(
                "bad-input", 1, 1, inputs=[{"prototype_id": "", "count": 1}]
            ))

    def test_invalid_measurement_is_rejected(self):
        for duration, start, end in (
            (math.nan, 0, 1),
            (60, math.inf, math.inf),
            (60, 10, 9),
        ):
            with self.subTest(duration=duration, start=start, end=end):
                with self.assertRaises(ValueError):
                    self.solver.measure_production_rate("gear", duration, start, end)


if __name__ == "__main__":
    unittest.main()
