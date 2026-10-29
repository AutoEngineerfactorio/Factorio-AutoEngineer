"""Production-flow tests use explicit synthetic data, never a live-world claim."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from production_flow import FlowProcess, FlowRequest, solve_flow, startable


class FlowValidationTests(unittest.TestCase):
    def test_unseeded_catalyst_cannot_start(self):
        p = FlowProcess("catalytic", {"ore": 1, "seed": 1}, {"plate": 1, "seed": 1}, 1)
        self.assertEqual(startable([p], FlowRequest({"plate": 1}, {"ore": 1})), [])
        r = FlowRequest({"plate": 1}, {"ore": 1}, seed_inventory={"seed": 1})
        self.assertEqual(startable([p], r), [p])

    def test_returning_one_catalyst_does_not_create_two_startup_items(self):
        a = FlowProcess("return", {"seed": 1}, {"seed": 1, "a": 1}, 1)
        b = FlowProcess("needs-two", {"seed": 2}, {"seed": 2, "b": 1}, 1)
        r = FlowRequest({"a": 1}, {}, seed_inventory={"seed": 1})
        self.assertEqual(startable([a, b], r), [a])

    def test_input_free_process_needs_explicit_source_evidence(self):
        with self.assertRaises(ValueError):
            FlowProcess("free-ore", {}, {"ore": 1}, 1)

    def test_invalid_numeric_values_fail_closed(self):
        for value in (True, float("nan"), float("inf"), -1, 1e13):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FlowRequest({"plate": value}, {})


class FlowSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            __import__("scipy")
        except ImportError:
            raise unittest.SkipTest("isolated solver dependencies unavailable")

    def test_chain_shares_coproduct_and_counts_whole_machines(self):
        processes = [FlowProcess("split", {"ore": 1}, {"a": 2, "b": 1}, 2),
                     FlowProcess("finish", {"a": 1, "b": 1}, {"final": 1}, 1)]
        result = solve_flow(processes, FlowRequest({"final": 3}, {"ore": 10}, {"a": 3}))
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["machines"], {"split": 2, "finish": 3})
        self.assertAlmostEqual(result["imports_per_second"]["ore"], 3)
        self.assertAlmostEqual(result["surplus_per_second"]["a"], 3)

    def test_byproducts_cannot_be_silently_voided(self):
        p = FlowProcess("split", {"ore": 1}, {"a": 1, "b": 1}, 1)
        result = solve_flow([p], FlowRequest({"a": 1}, {"ore": 10}))
        self.assertEqual(result["status"], "infeasible")

    def test_power_goal_selects_real_alternative(self):
        processes = [FlowProcess("fast", {"ore": 1}, {"a": 1}, 2, 1000),
                     FlowProcess("efficient", {"ore": 1}, {"a": 1}, 1, 100)]
        request = FlowRequest({"a": 2}, {"ore": 2}, power_budget_watts=250)
        result = solve_flow(processes, request, objective="power")
        self.assertEqual(result["machines"], {"efficient": 2})
        self.assertAlmostEqual(result["working_and_idle_watts"], 200)

    def test_inventory_is_not_a_sustained_supply(self):
        p = FlowProcess("make", {"ore": 1}, {"a": 1}, 1)
        result = solve_flow([p], FlowRequest({"a": 1}, {}, seed_inventory={"ore": 1000}))
        self.assertEqual(result["status"], "infeasible")

    def test_machine_cap_is_enforced(self):
        p = FlowProcess("make", {"ore": 1}, {"a": 1}, 1, max_machines=1)
        self.assertEqual(solve_flow([p], FlowRequest({"a": 2}, {"ore": 2}))["status"], "infeasible")


    def test_recycling_cannot_create_an_unseeded_supply(self):
        processes = [FlowProcess("a-b", {"a": 1}, {"b": 1}, 1),
                     FlowProcess("b-a", {"b": 1}, {"a": 2}, 1)]
        self.assertEqual(solve_flow(processes, FlowRequest({"a": 1}, {}))["status"], "infeasible")

    def test_seeded_catalyst_balance_reuses_returns(self):
        p = FlowProcess("make", {"ore": 1, "seed": 1}, {"a": 1, "seed": 1}, 2)
        result = solve_flow([p], FlowRequest({"a": 2}, {"ore": 2}, seed_inventory={"seed": 1}))
        self.assertEqual(result["status"], "estimated")
        self.assertNotIn("seed", result["imports_per_second"])

    def test_integer_idle_draw_can_make_power_infeasible(self):
        p = FlowProcess("make", {"ore": 1}, {"a": 1}, 1, 100, 10)
        result = solve_flow([p], FlowRequest({"a": 1.5}, {"ore": 2}, power_budget_watts=169))
        self.assertEqual(result["status"], "infeasible")

    def test_expected_yield_remains_explicitly_estimated(self):
        p = FlowProcess("chance", {"ore": 1}, {"a": .5}, 1, basis="expected")
        result = solve_flow([p], FlowRequest({"a": 1}, {"ore": 2}))
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["basis"], "expected")
        self.assertAlmostEqual(result["imports_per_second"]["ore"], 2)


    def test_reversed_large_chain_reaches_every_process(self):
        chain = [FlowProcess(str(i), {f"m{i}": 1}, {f"m{i+1}": 1}, 1)
                 for i in reversed(range(1000))]
        ready = startable(chain, FlowRequest({"m1000": 1}, {"m0": 1}))
        self.assertEqual([p.name for p in ready], [str(i) for i in range(1000)])

    def test_tiny_unmet_demand_is_not_accepted_as_zero_production(self):
        process = FlowProcess("make", {"ore": 1}, {"a": 1}, 1)
        result = solve_flow([process], FlowRequest({"a": 1e-12}, {"ore": 1}))
        if result["status"] == "estimated":
            self.assertGreater(result["crafts_per_second"].get("make", 0), 0)
        else:
            self.assertIn(result["status"], ("unavailable", "infeasible"))


    def test_scaled_high_yield_cannot_report_flow_without_a_machine(self):
        process = FlowProcess("huge-batch", {"ore": 1}, {"a": 1e12}, 1)
        result = solve_flow([process], FlowRequest({"a": 1}, {"ore": 1}))
        if result["status"] == "estimated":
            self.assertGreater(result["crafts_per_second"].get("huge-batch", 0), 0)
            self.assertEqual(result["machines"].get("huge-batch"), 1)
        else:
            self.assertIn(result["status"], ("unavailable", "infeasible"))


    def test_machine_inventory_is_shared_across_recipes(self):
        processes = [FlowProcess("a", {"ore": 1}, {"a": 1}, 1, machine_group="assembler"),
                     FlowProcess("b", {"ore": 1}, {"b": 1}, 1, machine_group="assembler")]
        request = FlowRequest({"a": 3, "b": 3}, {"ore": 6})
        self.assertEqual(solve_flow(processes, request,
            machine_limits={"assembler": 5})["status"], "infeasible")
        result = solve_flow(processes, request, machine_limits={"assembler": 6})
        self.assertEqual(sum(result["machines"].values()), 6)
