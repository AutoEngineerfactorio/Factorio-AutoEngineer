"""Mathematical 300 gears/minute fixture; no game execution."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from production_solver import ProductionSolver
from r06_fixture_chain import base_gears_chain, machine_stage


class TwoStageGearChain(unittest.TestCase):
    def test_300_gears_demand_and_realistic_machine_counts(self):
        proof = base_gears_chain()
        self.assertEqual(proof["evidence"], "offline-math-only")
        self.assertAlmostEqual(proof["target_gears_per_second"], 5)
        self.assertAlmostEqual(proof["required_iron_plates_per_second"], 10)
        self.assertAlmostEqual(proof["required_iron_ore_per_second"], 10)
        furnaces, assemblers = proof["stages"]
        self.assertEqual(furnaces["prototype"], "electric-furnace")
        self.assertEqual(furnaces["machines"], 16)
        self.assertAlmostEqual(furnaces["per_machine_items_per_second"], 0.625)
        self.assertAlmostEqual(furnaces["utilization_fraction"], 1)
        self.assertEqual(assemblers["prototype"], "assembling-machine-2")
        self.assertEqual(assemblers["machines"], 4)
        self.assertAlmostEqual(assemblers["per_machine_items_per_second"], 1.5)
        self.assertAlmostEqual(assemblers["utilization_fraction"], 5 / 6)
        self.assertEqual(proof["total_machine_count"], 20)
        self.assertAlmostEqual(proof["estimated_average_power_kw"], 3496)

    def test_solver_exposes_chain_not_just_a_hardcoded_number(self):
        fixture = ProductionSolver().get_fixture_proof("gears")
        self.assertEqual(fixture["chain"]["target_gears_per_minute"], 300)
        self.assertIn("not gameplay proof", fixture["notes"])

    def test_rate_scales_and_rounds_up(self):
        p = base_gears_chain(150)
        furnaces, assemblers = p["stages"]
        self.assertEqual(furnaces["machines"], 8)
        self.assertEqual(assemblers["machines"], 2)
        self.assertTrue(0 < assemblers["utilization_fraction"] <= 1)

    def test_bad_demand_and_power_fail_closed(self):
        for bad in (-1, 0, float("nan"), float("inf"), True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                base_gears_chain(bad)
        with self.assertRaises(ValueError):
            machine_stage(
                5, cycle_seconds=.5, crafting_speed=1, yield_per_cycle=1,
                active_kw=150, drain_kw=float("nan"), prototype="fixture"
            )
