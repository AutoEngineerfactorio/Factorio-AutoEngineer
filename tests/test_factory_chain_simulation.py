"""Test material and machine limits in synthetic steady-state production."""
import math
import sys
import unittest
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from factory_chain_simulation import constrained_second, make_constrained_trace
from factory_reality_test import evaluate_trace


class ConstrainedFactory(unittest.TestCase):
    def test_full_reference_chain(self):
        r = constrained_second()
        self.assertEqual(r["limiting_factor"], "none")
        p = r["products_per_second"]
        self.assertAlmostEqual(p["iron-plate"], 13)
        self.assertAlmostEqual(p["copper-plate"], 4.5)
        self.assertAlmostEqual(p["copper-cable"], 9)
        self.assertAlmostEqual(p["iron-gear-wheel"], 5)
        self.assertAlmostEqual(p["electronic-circuit"], 3)
        self.assertAlmostEqual(p["water"], 20)
        self.assertAlmostEqual(r["consumed_per_second"]["iron-plate"], 13)

    def test_shared_iron_shortage_reduces_both_targets(self):
        r = constrained_second(iron_ore_per_second=5.2)
        self.assertEqual(r["limiting_factor"], "iron_ore_supply")
        self.assertAlmostEqual(r["utilization_fraction"], 0.4)
        self.assertAlmostEqual(r["products_per_second"]["iron-gear-wheel"], 2)
        self.assertAlmostEqual(r["products_per_second"]["electronic-circuit"], 1.2)
        self.assertAlmostEqual(r["consumed_per_second"]["iron-plate"],
                               r["products_per_second"]["iron-plate"])

    def test_copper_bottleneck_restricts_shared_plan(self):
        r = constrained_second(copper_ore_per_second=2.25)
        self.assertEqual(r["limiting_factor"], "copper_ore_supply")
        self.assertAlmostEqual(r["products_per_second"]["iron-gear-wheel"], 2.5)
        self.assertAlmostEqual(r["products_per_second"]["electronic-circuit"], 1.5)

    def test_machine_undersupply_cannot_invent_output(self):
        r = constrained_second(iron_furnaces=10)
        self.assertEqual(r["limiting_factor"], "iron_furnaces")
        self.assertLess(r["products_per_second"]["iron-plate"], 6.26)
        self.assertLessEqual(r["products_per_second"]["iron-plate"],
                             r["available_ore_per_second"]["iron-ore"])

    def test_disconnected_transport_and_no_power_fail_closed(self):
        for args in ({"iron_transport_capacity": 0}, {"power_fraction": 0},
                     {"circuit_assemblers": 0}):
            with self.subTest(args=args):
                r = constrained_second(**args)
                self.assertEqual(r["utilization_fraction"], 0)
                self.assertEqual(r["products_per_second"]["iron-gear-wheel"], 0)

    def test_bad_inputs_rejected(self):
        for args in ({"iron_ore_per_second": -1},
                     {"copper_ore_per_second": math.nan},
                     {"power_fraction": 1.01},
                     {"gear_assemblers": True},
                     {"iron_furnaces": 10000},
                     {"iron_transport_capacity": math.inf}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                # Invalid types are intentionally supplied to the runtime validator.
                cast(Any, constrained_second)(**args)

    def test_ten_minute_trace_is_recipe_balance_constrained(self):
        trace = make_constrained_trace()
        report = evaluate_trace(trace)
        self.assertFalse(report["live_game_verified"])
        self.assertEqual(trace["evidence"], "synthetic_fixture")
        self.assertEqual(report["sample_count"], 601)
        by_name = {p["name"]: p for p in report["products"]}
        self.assertEqual(len(by_name), 6)
        self.assertEqual(by_name["iron-gear-wheel"]["windows_minutes"]["1"]["observed_rate"],
                         300)
        self.assertEqual(by_name["iron-gear-wheel"]["windows_minutes"]["5"]["observed_rate"],
                         228)
        self.assertEqual(by_name["iron-gear-wheel"]["windows_minutes"]["10"]["observed_rate"],
                         264)
        self.assertEqual(by_name["electronic-circuit"]["windows_minutes"]["5"]["observed_rate"],
                         136.8)
        self.assertEqual(by_name["water"]["windows_minutes"]["10"]["observed_rate"], 1200)
        consumed = by_name["iron-plate"]["windows_minutes"]["10"]["consumed"]
        made = by_name["iron-plate"]["windows_minutes"]["10"]["produced"]
        self.assertAlmostEqual(made, consumed)
        self.assertEqual(report["minimum_power_satisfaction"], 0.55)

    def test_trace_has_no_phantom_intermediate_material(self):
        trace = make_constrained_trace()
        end = trace["samples"][-1]
        produced = {item["name"]: item["total"] for item in end["produced"]}
        consumed = {item["name"]: item["total"] for item in end["consumed"]}
        self.assertAlmostEqual(produced["iron-plate"], consumed["iron-plate"])
        self.assertAlmostEqual(produced["copper-plate"], consumed["copper-plate"])
        self.assertAlmostEqual(produced["copper-cable"], consumed["copper-cable"])


if __name__ == "__main__":
    unittest.main()
