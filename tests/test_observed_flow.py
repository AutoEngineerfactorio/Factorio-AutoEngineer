"""Synthetic observed-catalog adapter coverage; no live acceptance implied."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from observed_flow import recipe_flow, solve_observed_flow
from production_flow import FlowRequest
from qt_catalog import CatalogSnapshot


def catalog():
    return CatalogSnapshot(recipes=({"name": "make", "enabled": True, "hidden": False,
        "category": "crafting", "crafting_time": .5,
        "ingredients": [{"type": "item", "name": "ore", "amount": 2}],
        "products": [{"type": "item", "name": "plate", "amount": 1}]},),
        machines=({"name": "machine", "crafting_categories": ["crafting"],
                   "crafting_speed": 1, "energy_usage": 100},), research=(),
        status="assembled", detail="fixture", state="observed", total_count=1,
        total_pages=1, page=1, truncated=False, source_fingerprint="fixture",
        game_version="2.1.23", force="player", surface="nauvis", tick=1)


class ObservedFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            __import__("scipy")
        except ImportError:
            raise unittest.SkipTest("isolated solver dependencies unavailable")

    def test_actual_machine_speed_and_power_bind_to_recipe(self):
        result = solve_observed_flow(catalog(), FlowRequest({"item:plate": 2}, {"item:ore": 4}))
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["machines"], {"make @ machine": 1})
        self.assertEqual(result["working_watts_excluding_unknown_drain"], 100)
        self.assertEqual(result["source_fingerprint"], "fixture")

    def test_stale_catalog_is_rejected(self):
        with self.assertRaises(ValueError):
            solve_observed_flow(replace(catalog(), state="stale"), FlowRequest({"item:plate": 1}, {}))

    def test_unknown_drain_cannot_satisfy_a_power_budget(self):
        result = solve_observed_flow(catalog(), FlowRequest({"item:plate": 1}, {"item:ore": 4},
                                                           power_budget_watts=1000))
        self.assertEqual(result["status"], "infeasible")

    def test_unknown_temperature_route_is_not_simplified(self):
        recipe = dict(catalog().recipes[0])
        recipe["products"] = [{"type": "fluid", "name": "steam", "amount": 10, "temperature": 500}]
        with self.assertRaisesRegex(ValueError, "Thermal"):
            recipe_flow(recipe, False)


    def test_observed_idle_drain_is_validated_and_constrains_the_plan(self):
        from read_only_planning import validate_machines

        rows = validate_machines({"machines": [dict(catalog().machines[0], energy_drain=10)]})
        observed = replace(catalog(), machines=tuple(rows))
        result = solve_observed_flow(observed, FlowRequest({"item:plate": 2}, {"item:ore": 4},
                                                          power_budget_watts=109))
        self.assertEqual(result["status"], "infeasible")
        result = solve_observed_flow(observed, FlowRequest({"item:plate": 2}, {"item:ore": 4},
                                                          power_budget_watts=110))
        self.assertEqual(result["working_and_idle_watts"], 110)
        with self.assertRaisesRegex(ValueError, "idle drain"):
            validate_machines({"machines": [dict(catalog().machines[0], energy_drain=-1)]})


    def test_quality_eligible_products_keep_normal_zero_bonus_estimate(self):
        source = catalog()
        recipe = dict(source.recipes[0])
        recipe["products"] = [dict(recipe["products"][0], affected_by_quality=True)]
        observed = replace(source, recipes=(recipe,))
        result = solve_observed_flow(observed, FlowRequest({"item:plate": 2}, {"item:ore": 4}))
        self.assertEqual(result["status"], "estimated")
        self.assertIn("Normal quality and base recipe yields", result["assumptions"])


    def test_two_observed_recipes_cannot_reuse_one_machine_stock(self):
        source = catalog()
        second = dict(source.recipes[0], name="make-wire",
                      products=[{"type": "item", "name": "wire", "amount": 1}])
        source = replace(source, recipes=source.recipes + (second,), total_count=2)
        request = FlowRequest({"item:plate": 1, "item:wire": 1}, {"item:ore": 4})
        result = solve_observed_flow(source, request, machine_limits={"machine": 1})
        self.assertEqual(result["status"], "infeasible")


    def test_external_supply_does_not_qualify_an_unobserved_prototype(self):
        request = FlowRequest({"item:not-a-real-prototype": 1}, {"item:not-a-real-prototype": 1})
        with self.assertRaisesRegex(ValueError, "identity not present"):
            solve_observed_flow(catalog(), request)


    def test_empty_lua_machine_arrays_are_preserved_but_nonempty_maps_rejected(self):
        from read_only_planning import validate_machines

        fields = ("fluid_boxes", "allowed_effects", "allowed_module_categories")
        raw = dict(catalog().machines[0], **{name: {} for name in fields})
        checked = validate_machines({"machines": [raw]})[0]
        for name in fields:
            self.assertEqual(checked[name], [])
            bad = dict(raw, **{name: {"unexpected": True}})
            with self.assertRaises(ValueError):
                validate_machines({"machines": [bad]})
