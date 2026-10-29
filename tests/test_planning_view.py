import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from planning_view import RecipeResearchView, catalog_view_model
from read_only_planning import view_intelligence
from recipe_material_planner import format_target_production, plan_target_production


class CatalogViewModelTests(unittest.TestCase):
    def test_lists_observed_item_and_fluid_recipe_data(self):
        recipe = {
            "name": "sulfuric-acid",
            "enabled": True,
            "hidden": False,
            "simple": False,
            "category": "chemistry",
            "crafting_time": 1.0,
            "ingredients": [
                {"name": "water", "type": "fluid", "amount": 100},
                {"name": "iron-plate", "type": "item", "amount": 1},
            ],
            "products": [{"name": "sulfuric-acid", "type": "fluid", "amount": 50}],
            "unlock_technologies": [
                {"name": "oil-processing", "researched": True, "enabled": True},
                {"name": "advanced-oil-processing", "researched": False, "enabled": True},
            ],
        }
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Planning disabled: profile is not qualified",
            "catalog_status": {
                "status": "assembled",
                "total_count": 1,
            },
            "capabilities": {
                "game_version": "2.1.23",
                "force": "player",
                "surface": "nauvis",
                "tick": 900,
                "enabled_content": ["base"],
                "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
                "recipes": [recipe],
                "research": ["oil-processing"],
            },
            "mechanics": {
                "categories_with_evidence": 3,
                "total_categories": 13,
                "dimension_counts": {
                    "observed": 3,
                    "verified": 0,
                    "regression_passed": 0,
                },
            },
        })

        self.assertIn("Planning disabled", model["status"])
        self.assertIn("Complete catalog: 1 recipes", model["metadata"])
        self.assertIn("Source change fingerprint:", model["metadata"])
        self.assertIn("(not authentication)", model["metadata"])
        self.assertIn("3/13 categories have evidence", model["metadata"])
        self.assertEqual(model["research"], ["oil-processing"])
        # The recipe carries an unlock technology that is not researched, so
        # it is locked rather than enabled.
        self.assertEqual(model["recipes"][0]["availability"], "Locked")
        self.assertEqual(model["recipes"][0]["feasibility_status"], "locked")
        self.assertEqual(
            model["recipes"][0]["ingredients"],
            "100 fluid:water, 1 item:iron-plate",
        )
        self.assertEqual(model["recipes"][0]["products"], "50 fluid:sulfuric-acid")
        self.assertIn("sulfuric-acid", model["recipes"][0]["search"])
        self.assertIn("advanced-oil-processing", model["recipes"][0]["search"])
        self.assertIn("advanced-oil-processing", model["recipes"][0]["unlock_summary"])
        self.assertEqual(
            [unlock["name"] for unlock in model["recipes"][0]["recipe"]["unlock_technologies"]],
            ["oil-processing", "advanced-oil-processing"],
        )

    def test_partial_catalog_and_disabled_state_are_explicit(self):
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Recipe catalog pages are not fully assembled",
            "catalog_status": {
                "status": "ok",
                "page": 2,
                "total_pages": 4,
                "total_count": 60,
            },
            "capabilities": {
                "game_version": "2.1.23",
                "force": "player",
                "surface": "nauvis",
                "tick": 901,
                "recipes": [{
                    "name": "locked-recipe",
                    "enabled": False,
                    "hidden": False,
                    "simple": False,
                    "category": "crafting",
                    "crafting_time": 1,
                    "ingredients": [],
                    "products": [{"name": "locked-item", "type": "item", "amount": 1}],
                }],
                "research": [],
            },
        })

        self.assertIn("Partial catalog page 2 of 4", model["metadata"])
        self.assertEqual(model["recipes"][0]["availability"], "Disabled")
        self.assertIn("Planning disabled", model["status"])

    def test_missing_capabilities_are_not_rendered_as_a_catalog(self):
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Version/research/recipe catalog unavailable",
            "capabilities": None,
        })

        self.assertEqual(model["recipes"], [])
        self.assertEqual(model["research"], [])
        self.assertIn("unavailable", model["status"].lower())

    def test_assembled_pages_do_not_hide_truncated_snapshot(self):
        model = catalog_view_model({
            "planner_ready": False,
            "reason": "Recipe catalog empty/truncated: planning disabled",
            "catalog_status": {"status": "assembled"},
            "capabilities": {
                "game_version": "2.1.23",
                "force": "player",
                "surface": "nauvis",
                "tick": 902,
                "truncated": True,
                "recipes": [],
                "research": [],
                "enabled_content": [],
            },
        })

        self.assertIn("snapshot data is truncated", model["metadata"])


class RecipeMechanicsViewTests(unittest.TestCase):
    """The Recipes and Research tab must show the observed mechanics.

    The tab must not hide a recipe because of an unsupported mechanic, and
    it must show the effective yield rather than only the nominal amount.
    """

    @staticmethod
    def _model(recipes, research=()):
        return catalog_view_model({
            "planner_ready": True,
            "catalog_status": {"status": "assembled", "total_count": len(recipes)},
            "capabilities": {
                "game_version": "2.1.23",
                "force": "player",
                "surface": "nauvis",
                "tick": 900,
                "enabled_content": ["base"],
                "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
                "recipes": recipes,
                "research": list(research),
            },
            "mechanics": {"dimension_counts": {}},
        })

    def test_a_ranged_product_shows_its_bounds(self):
        model = self._model([{
            "name": "mining",
            "enabled": True, "hidden": False, "simple": False,
            "category": "mining", "crafting_time": 1,
            "ingredients": [{"name": "rock", "type": "item", "amount": 1}],
            "products": [{"name": "ore", "type": "item", "amount": 1,
                          "amount_min": 1, "amount_max": 3}],
        }])

        row = model["recipes"][0]
        self.assertIn("1-3", row["products"])
        self.assertTrue(row["yield_uncertain"])

    def test_a_probabilistic_product_shows_its_probability(self):
        model = self._model([{
            "name": "lucky",
            "enabled": True, "hidden": False, "simple": False,
            "category": "crafting", "crafting_time": 1,
            "ingredients": [],
            "products": [{"name": "gem", "type": "item", "amount": 1,
                          "independent_probability": 0.25}],
        }])

        row = model["recipes"][0]
        self.assertIn("25%", row["products"])
        self.assertTrue(row["yield_uncertain"])

    def test_a_fixed_product_shows_its_plain_amount(self):
        model = self._model([{
            "name": "smelting",
            "enabled": True, "hidden": False, "simple": True,
            "category": "crafting", "crafting_time": 1,
            "ingredients": [{"name": "ore", "type": "item", "amount": 1}],
            "products": [{"name": "plate", "type": "item", "amount": 1}],
        }])

        row = model["recipes"][0]
        self.assertEqual(row["products"], "1 item:plate")
        self.assertFalse(row["yield_uncertain"])

    def test_a_research_locked_recipe_is_shown_as_locked(self):
        model = self._model([{
            "name": "advanced-gear",
            "enabled": True, "hidden": False, "simple": True,
            "category": "crafting", "crafting_time": 1,
            "ingredients": [],
            "products": [{"name": "gear", "type": "item", "amount": 1}],
            "unlock_technologies": [
                {"name": "advanced-processing", "researched": False, "enabled": True},
            ],
        }], research=["automation"])

        row = model["recipes"][0]
        self.assertEqual(row["availability"], "Locked")
        self.assertEqual(row["feasibility_status"], "locked")

    def test_a_researched_recipe_is_shown_as_available(self):
        model = self._model([{
            "name": "advanced-gear",
            "enabled": True, "hidden": False, "simple": True,
            "category": "crafting", "crafting_time": 1,
            "ingredients": [],
            "products": [{"name": "gear", "type": "item", "amount": 1}],
            "unlock_technologies": [
                {"name": "advanced-processing", "researched": True, "enabled": True},
            ],
        }], research=["advanced-processing"])

        row = model["recipes"][0]
        self.assertEqual(row["feasibility_status"], "available")

    def test_a_fluid_temperature_requirement_is_shown(self):
        model = self._model([{
            "name": "boiler",
            "enabled": True, "hidden": False, "simple": False,
            "category": "chemistry", "crafting_time": 1,
            "ingredients": [{"name": "water", "type": "fluid", "amount": 100,
                             "minimum_temperature": 15,
                             "maximum_temperature": 100}],
            "products": [{"name": "steam", "type": "fluid", "amount": 100,
                          "temperature": 15}],
        }])

        row = model["recipes"][0]
        self.assertIn("15", row["ingredients"])
        self.assertIn("temperature", row["ingredients"].lower())

    def test_a_quality_restriction_is_shown(self):
        model = self._model([{
            "name": "quality-plate",
            "enabled": True, "hidden": False, "simple": False,
            "category": "crafting", "crafting_time": 1,
            "ingredients": [],
            "products": [{"name": "plate", "type": "item", "amount": 1,
                          "quality_min": "normal", "quality_max": "legendary"}],
        }])

        row = model["recipes"][0]
        self.assertIn("normal", row["products"])
        self.assertIn("legendary", row["products"])

    def test_a_productivity_restriction_is_shown(self):
        model = self._model([{
            "name": "restricted",
            "enabled": True, "hidden": False, "simple": False,
            "category": "crafting", "crafting_time": 1,
            "ingredients": [],
            "products": [{"name": "plate", "type": "item", "amount": 1,
                          "ignored_by_productivity": 1}],
        }])

        row = model["recipes"][0]
        self.assertIn("productivity", row["products"].lower())

    def test_the_unsupported_mechanics_are_summarised(self):
        model = self._model([{
            "name": "ranged",
            "enabled": True, "hidden": False, "simple": False,
            "category": "mining", "crafting_time": 1,
            "ingredients": [],
            "products": [{"name": "ore", "type": "item", "amount": 1,
                          "amount_min": 1, "amount_max": 3}],
        }])

        self.assertTrue(model["unsupported_mechanics"])
        self.assertTrue(
            any("range" in reason.lower() or "expected" in reason.lower()
                for reason in model["unsupported_mechanics"])
        )

    def test_the_recipe_row_is_searchable_by_its_mechanics(self):
        model = self._model([{
            "name": "boiler",
            "enabled": True, "hidden": False, "simple": False,
            "category": "chemistry", "crafting_time": 1,
            "ingredients": [{"name": "water", "type": "fluid", "amount": 100,
                             "minimum_temperature": 15}],
            "products": [{"name": "steam", "type": "fluid", "amount": 100}],
        }])

        self.assertIn("temperature", model["recipes"][0]["search"])


class ProductionTargetViewTests(unittest.TestCase):
    """The tab must offer a production target in items/sec and items/min.

    The Tk widget itself needs a display, so these tests pin the logic that
    the widget calls and the wiring that the widget depends on.
    """

    @staticmethod
    def _intelligence(recipes):
        """Build a qualified observation through the real envelope validator."""
        raw = {
            "schema": 1,
            "tick": 900,
            "surface": "nauvis",
            "game_version": "2.1.23",
            "force": "player",
            "research": [],
            "enabled_content": ["base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": recipes,
        }
        return view_intelligence({
            "status": "ok",
            "tick": 900,
            "surface": "nauvis",
            "position": {"x": 0, "y": 0},
            "inventory": [],
            "inventory_available": True,
            "truncated": False,
            "capabilities": raw,
            "catalog_status": {"status": "assembled", "total_count": len(recipes)},
        }, received_at=100)

    @staticmethod
    def _recipe(name, products, crafting_time=1.0):
        return {
            "name": name,
            "enabled": True, "hidden": False, "simple": False,
            "category": "crafting", "crafting_time": crafting_time,
            "ingredients": [{"name": "ore", "type": "item", "amount": 1}],
            "products": products,
        }

    def test_a_per_second_target_is_planned(self):
        observed = self._intelligence([
            self._recipe("plate", [
                {"name": "plate", "type": "item", "amount": 1},
            ], crafting_time=2.0),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_second=2.0, machine_speed=1.0,
        )

        self.assertEqual(plan["requested_per_second"], 2.0)
        self.assertEqual(plan["requested_per_minute"], 120.0)
        self.assertEqual(plan["achievable_per_second"], 0.5)
        self.assertEqual(plan["machine_count"], 4.0)

    def test_a_per_minute_target_is_planned(self):
        observed = self._intelligence([
            self._recipe("plate", [
                {"name": "plate", "type": "item", "amount": 1},
            ], crafting_time=1.0),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_minute=60.0, machine_speed=1.0,
        )

        self.assertEqual(plan["requested_per_second"], 1.0)
        self.assertEqual(plan["requested_per_minute"], 60.0)

    def test_the_formatted_target_shows_both_rate_units(self):
        observed = self._intelligence([
            self._recipe("plate", [
                {"name": "plate", "type": "item", "amount": 1},
            ], crafting_time=1.0),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_second=2.0, machine_speed=1.0,
        )
        text = format_target_production(plan)

        self.assertIn("2 /s", text)
        self.assertIn("120 /min", text)
        self.assertIn("Machine count: 2", text)

    def test_an_alternative_production_path_is_shown(self):
        observed = self._intelligence([
            self._recipe("fast", [
                {"name": "plate", "type": "item", "amount": 1},
            ], crafting_time=0.5),
            self._recipe("slow", [
                {"name": "plate", "type": "item", "amount": 1},
            ], crafting_time=2.0),
        ])

        plan = plan_target_production(
            observed, "item", "plate", per_second=1.0, machine_speed=1.0,
        )
        text = format_target_production(plan)

        self.assertIn("Alternative production paths:", text)
        self.assertIn("slow", text)

    def test_a_missing_machine_speed_is_shown_as_not_established(self):
        observed = self._intelligence([
            self._recipe("plate", [
                {"name": "plate", "type": "item", "amount": 1},
            ], crafting_time=1.0),
        ])

        plan = plan_target_production(observed, "item", "plate", per_second=1.0)
        text = format_target_production(plan)

        self.assertIn("Not established:", text)
        self.assertIn("machine", text)

    def test_the_view_uses_a_worker_thread_for_the_catalog_model(self):
        """The catalog model must not be built on the Tkinter main thread."""
        import inspect

        source = inspect.getsource(RecipeResearchView.update_intelligence)
        self.assertIn("threading.Thread", source)
        self.assertIn(
            "self.after(",
            inspect.getsource(RecipeResearchView._poll_model),
        )

    def test_the_view_offers_a_per_second_and_per_minute_unit(self):
        import inspect

        source = inspect.getsource(RecipeResearchView.__init__)
        self.assertIn("per_second", source)
        self.assertIn("per_minute", source)

    def test_a_fast_frame_rate_cannot_start_a_second_model_build(self):
        """Only one model build may run at a time."""
        import inspect

        source = inspect.getsource(RecipeResearchView.update_intelligence)
        self.assertIn("self._model_building", source)
        self.assertIn("self._pending_intelligence", source)

    def test_a_superseded_model_is_discarded(self):
        import inspect

        source = inspect.getsource(RecipeResearchView._poll_model)
        self.assertIn("generation != self._model_generation", source)


class CatalogModelShapeTests(unittest.TestCase):
    """The catalog model must always carry the same keys.

    A live GUI run proved the defect: the empty model returned no
    ``unresearched_technologies`` key and the view raised a KeyError while
    applying it.
    """

    #: The keys every catalog model carries.
    REQUIRED_KEYS = (
        "status", "metadata", "recipes", "research",
        "unresearched_technologies", "unsupported_mechanics",
    )

    def test_the_empty_model_carries_every_key(self):
        model = catalog_view_model({"status": "unavailable"})
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, model)
        self.assertEqual(model["unresearched_technologies"], {})
        self.assertEqual(model["unsupported_mechanics"], [])

    def test_the_full_model_carries_every_key(self):
        model = catalog_view_model({
            "planner_ready": True,
            "catalog_status": {"status": "assembled"},
            "capabilities": {
                "game_version": "2.1.23",
                "force": "player",
                "surface": "nauvis",
                "tick": 900,
                "enabled_content": ["base"],
                "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
                "recipes": [],
                "research": [],
            },
            "mechanics": {"dimension_counts": {}},
        })
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, model)

    def test_the_view_does_not_raise_on_an_empty_model(self):
        """Every key the view reads must exist on the empty model."""
        import inspect

        source = inspect.getsource(RecipeResearchView._poll_model)
        # The keys the view reads out of the model.
        for key in ("status", "metadata", "recipes", "research",
                    "unresearched_technologies"):
            self.assertIn(key, source)
        # The empty model provides every one of them.
        empty = catalog_view_model({"status": "unavailable"})
        for key in ("status", "metadata", "recipes", "research",
                    "unresearched_technologies"):
            self.assertIn(key, empty)


class CatalogRefreshRegressionTests(unittest.TestCase):
    def test_stale_worker_result_starts_pending_model_instead_of_polling_forever(self):
        from queue import Queue
        from unittest.mock import Mock
        view = Mock()
        view._model_queue = Queue()
        view._model_queue.put((1, {"status": "stale"}))
        view._model_generation = 2
        view._model_building = True
        view._pending_intelligence = {"status": "latest"}
        RecipeResearchView._poll_model(view)
        self.assertFalse(view._model_building)
        self.assertIsNone(view._pending_intelligence)
        view.update_intelligence.assert_called_once_with({"status": "latest"})
        view.after.assert_not_called()

    def test_pyanodons_catalog_renders_at_most_250_but_searches_all(self):
        from unittest.mock import Mock
        view = Mock()
        view.recipe_list.selection.return_value = ()
        view.recipe_list.get_children.return_value = ()
        view.search.get.return_value = ""
        view.model = {
            "status": "Ready",
            "recipes": [
                dict(name=f"recipe-{i}", search=f"recipe-{i}",
                     availability="Available", category="crafting",
                     products="1 item:test", unlock_summary="")
                for i in range(10000)
            ] + [
                dict(name="special-tail", search="special-tail",
                     availability="Available", category="crafting",
                     products="1 item:test", unlock_summary="")
            ],
        }
        RecipeResearchView.populate_recipes(view)
        self.assertEqual(view.recipe_list.insert.call_count, 250)
        self.assertIn("Showing 250/10001", view.status.set.call_args.args[0])
        view.recipe_list.insert.reset_mock()
        view.search.get.return_value = "special-tail"
        RecipeResearchView.populate_recipes(view)
        self.assertEqual(view.recipe_list.insert.call_count, 1)
        self.assertEqual(view.recipe_list.insert.call_args.kwargs["iid"], "special-tail")


if __name__ == "__main__":
    unittest.main()
