"""Offline stress-harness regressions; these do not assert pY compatibility."""
import unittest

from benchmarks.modded_recipe_graph import build_synthetic_profile, run_benchmark


class TestSyntheticModdedRecipeBenchmark(unittest.TestCase):
    def test_input_bounds(self):
        for size in (0, -1, 50001):
            with self.assertRaises(ValueError):
                build_synthetic_profile(size)

    def test_wide_graph_with_alternatives_cycles_and_byproducts(self):
        solver = build_synthetic_profile(200)
        graph = solver.compute_recipe_graph("benchmark-target", {}, float("inf"))
        self.assertTrue(graph["found"])
        self.assertFalse(graph["truncated"])
        self.assertIn("intermediate-0-alternative", graph["graph"])
        self.assertIn("raw-feed", graph["graph"])
        self.assertGreaterEqual(len(graph["cycles"]), 2)
        self.assertEqual(len(solver.recipes["intermediate-0"].byproducts), 1)

    def test_report_does_not_claim_mod_validation(self):
        report = run_benchmark(30)
        self.assertEqual(report["dataset"], "synthetic-modded-v1")
        self.assertFalse(report["actual_pyanodons_data"])
        self.assertEqual(report["recipe_count"], 30)
        self.assertFalse(report["truncated"])
        self.assertEqual(report["graph_nodes"], 30 + 6 + 2)


if __name__ == "__main__":
    unittest.main()
