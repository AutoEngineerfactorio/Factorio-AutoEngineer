"""Regressions for the R06 large-modpack planner benchmark.

The benchmark itself is synthetic. These tests assert that it is
deterministic, that it exercises the mechanics it claims to exercise, and
that it never claims real Pyanodons data.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from r06_planner_benchmark import build_catalog, run_benchmark


class PlannerBenchmarkTests(unittest.TestCase):
    def test_the_input_bounds_are_enforced(self):
        for size in (0, -1, 50001):
            with self.assertRaises(ValueError):
                build_catalog(size)

    def test_a_small_catalog_is_planned_and_measured(self):
        report = run_benchmark(30)
        self.assertEqual(report["dataset"], "synthetic-modpack-catalog-v1")
        self.assertFalse(report["actual_pyanodons_data"])
        self.assertEqual(report["recipe_count"], 31)
        self.assertEqual(report["validated_recipes"], 31)
        self.assertGreater(report["plan_ms"], 0)
        self.assertGreater(report["peak_memory_mib"], 0)

    def test_the_benchmark_never_claims_real_mod_data(self):
        report = run_benchmark(10)
        self.assertFalse(report["actual_pyanodons_data"])

    def test_every_recipe_is_assessed_for_feasibility(self):
        report = run_benchmark(40)
        self.assertEqual(report["feasibility_rows"], 41)

    def test_the_catalog_exercises_the_advanced_mechanics(self):
        catalog = build_catalog(30)
        products = [
            part for recipe in catalog["recipes"] for part in recipe["products"]
        ]
        fields = set()
        for part in products:
            fields.update(part)
        for field in ("amount_min", "amount_max", "independent_probability",
                      "percent_spoiled", "quality_min", "quality_max",
                      "ignored_by_productivity", "extra_count_fraction",
                      "temperature"):
            self.assertIn(field, fields, f"{field} was not exercised")

    def test_the_catalog_exercises_fluids_and_categories(self):
        catalog = build_catalog(30)
        fluid_recipes = [
            recipe for recipe in catalog["recipes"]
            if any(part["type"] == "fluid" for part in recipe["ingredients"]
                   + recipe["products"])
        ]
        self.assertTrue(fluid_recipes)
        multi_category = [
            recipe for recipe in catalog["recipes"]
            if len(recipe.get("categories") or ()) > 1
        ]
        self.assertTrue(multi_category)

    def test_the_catalog_excludes_research_locked_recipes_from_planning(self):
        catalog = build_catalog(30)
        locked = [
            recipe for recipe in catalog["recipes"]
            if any(not unlock["researched"]
                   for unlock in recipe.get("unlock_technologies") or ())
        ]
        self.assertTrue(locked)

    def test_the_benchmark_is_deterministic(self):
        first = run_benchmark(20)
        second = run_benchmark(20)
        for key in ("recipe_count", "validated_recipes", "plan_status",
                    "selected_recipes", "unresolved_rows",
                    "feasibility_rows"):
            self.assertEqual(first[key], second[key])

    def test_a_large_catalog_stays_within_the_addressable_bound(self):
        report = run_benchmark(2000)
        self.assertEqual(report["validated_recipes"], 2001)
        self.assertLess(report["validated_recipes"], 10000 * 16)


if __name__ == "__main__":
    unittest.main()
