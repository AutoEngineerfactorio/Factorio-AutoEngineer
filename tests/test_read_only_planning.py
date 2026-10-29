"""Read-only R04-R06 integration and legacy gameplay-entry safety regressions."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from dashboard_feed import PREFIX, parse_frame, snapshot
from read_only_planning import (
    machine_options,
    plan_blueprint,
    plan_recipe_production,
    plan_stochastic_recipe,
    preview_simple_recipe,
    validate_capabilities,
    view_intelligence,
)
from safe_executor import main as legacy_executor_main


def frame():
    return {
        "status": "ok", "x": 0.0, "y": 2.0, "position": {"x": 0, "y": 2},
        "tick": 120, "surface": "nauvis", "inventory": [
            {"name": "iron-plate", "quality": "normal", "count": 30},
        ], "inventory_available": True, "truncated": False,
    }


def caps():
    return {
        "schema": 1, "tick": 120, "surface": "nauvis", "game_version": "2.1.23",
        "force": "player", "research": ["automation"], "enabled_content": ["base"],
        "truncated": False,
        "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
        "recipes": [
            {"name": "iron-gear-wheel", "enabled": True, "hidden": False, "simple": True,
             "category": "crafting", "crafting_time": 0.5,
             "ingredients": [{"type": "item", "name": "iron-plate", "amount": 2}],
             "products": [{"type": "item", "name": "iron-gear-wheel", "amount": 1}]},
        ],
    }


class ReadOnlyObservations(unittest.TestCase):
    def test_current_backend_is_observed_but_not_recipe_ready(self):
        result = view_intelligence(dict(status='ok', **snapshot(frame())), received_at=100)
        self.assertEqual(result["status"], "observed")
        self.assertFalse(result["planner_ready"])
        self.assertIsNone(result["capabilities"])
        self.assertEqual(result["mechanics"]["dimension_counts"]["verified"], 0)
        self.assertEqual(result["mechanics"]["dimension_counts"]["observed"], 2)
        self.assertEqual(result["mechanics"]["dimension_counts"]["action_permitted"], 0)

    def test_missing_and_partial_inventory_never_claims_verified(self):
        raw = frame()
        raw["inventory_available"] = False
        observed = view_intelligence(dict(status='ok', **snapshot(raw)), received_at=100)
        self.assertEqual(observed["mechanics"]["dimension_counts"]["observed"], 1)
        raw["inventory_available"] = True
        raw["truncated"] = True
        observed = view_intelligence(dict(status='ok', **snapshot(raw)), received_at=100)
        self.assertFalse(observed["planner_ready"])
        self.assertEqual(observed["mechanics"]["dimension_counts"]["verified"], 0)

    def test_unavailable_frame_disables_planning(self):
        result = view_intelligence({"status": "unavailable"})
        self.assertFalse(result["planner_ready"])

    def test_same_tick_catalog_can_roundtrip_through_child_frame(self):
        raw = frame()
        raw["capabilities"] = caps()
        wire = dict(schema=1, status="ok", **snapshot(raw), visited=[], failed=[],
                    resources=[], objective=None, proposal=None)
        parsed = parse_frame(PREFIX + json.dumps(wire))
        result = view_intelligence(parsed, received_at=100)
        self.assertTrue(result["planner_ready"])
        self.assertEqual(result["capabilities"]["recipes"][0]["name"], "iron-gear-wheel")
        self.assertEqual(result["mechanics"]["dimension_counts"]["verified"], 0)
        self.assertEqual(result["mechanics"]["dimension_counts"]["action_permitted"], 0)
        self.assertEqual(result["status"], "live")

    def test_modified_mods_recipes_or_research_change_fingerprint(self):
        a = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=caps()))), received_at=100)
        changed = caps()
        changed["enabled_content"] = ["base", "quality"]
        b = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=changed))), received_at=100)
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])
        changed = caps()
        changed["recipes"][0]["ingredients"][0]["amount"] = 3
        c = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=changed))), received_at=100)
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])
        changed = caps()
        changed["recipes"][0]["unlock_technologies"] = [
            {"name": "automation-2", "researched": False, "enabled": True},
        ]
        d = view_intelligence(
            dict(status='ok', **snapshot(dict(frame(), capabilities=changed))),
            received_at=100,
        )
        self.assertNotEqual(a["fingerprint"], d["fingerprint"])

    def test_catalog_fingerprint_is_stable_across_game_ticks(self):
        first = dict(status="ok", **snapshot(dict(frame(), capabilities=caps())))
        later_frame = dict(frame(), tick=121)
        later_caps = dict(caps(), tick=121)
        later = dict(status="ok", **snapshot(dict(later_frame, capabilities=later_caps)))
        a = view_intelligence(first, received_at=100)
        b = view_intelligence(later, received_at=101)
        self.assertEqual(a["fingerprint"], b["fingerprint"])

    def test_wrong_surface_tick_truncated_and_bad_metadata_fail_closed(self):
        cases = [
            {"tick": 119},
            {"surface": "vulcanus"},
            {"truncated": "false"},
            {"game_version": "1.1.10"},
            {"recipes": [{"name": "gear"}]},
        ]
        for update in cases:
            p = dict(caps(), **update)
            with self.subTest(update=str(update)), self.assertRaises(ValueError):
                snapshot(dict(frame(), capabilities=p))
        p = caps()
        p["truncated"] = True
        self.assertFalse(view_intelligence(
            snapshot(dict(frame(), capabilities=p)), received_at=100)["planner_ready"])

    def test_recipe_pagination_empty_or_missing_is_not_ready(self):
        p = caps()
        p["recipes"] = []
        result = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=p))), received_at=100)
        self.assertFalse(result["planner_ready"])
        with self.assertRaises(ValueError):
            validate_capabilities(dict(caps(), recipes=[caps()["recipes"][0]] * 129), "nauvis", 120)

    def test_empty_factorio_tables_and_hidden_recipes_are_safe(self):
        p = caps()
        p["research"] = {}
        p["recipes"] = {}
        parsed = validate_capabilities(p, "nauvis", 120)
        self.assertEqual(parsed["research"], [])
        self.assertEqual(parsed["recipes"], [])
        self.assertFalse(view_intelligence(
            dict(status="ok", **snapshot(dict(frame(), capabilities=p))), received_at=100
        )["planner_ready"])

        p = caps()
        p["recipes"][0]["hidden"] = True
        p["recipes"][0]["simple"] = False
        parsed = validate_capabilities(p, "nauvis", 120)
        with self.assertRaises(ValueError):
            preview_simple_recipe(
                parsed, "iron-gear-wheel", machine_speed=1, machine_power_kw=100,
                input_rates={"iron-plate": 100}, power_kw=1000, target_rate=5)

    def test_catalog_source_fingerprint_is_validated(self):
        for value in ("", "poly31x131-v1:short", "sha256:" + "0" * 64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_capabilities(dict(caps(), source_fingerprint=value), "nauvis", 120)

    def test_recipe_category_is_required_and_bounded(self):
        for category in (None, "", "bad\ncategory", 12):
            with self.subTest(category=category), self.assertRaises(ValueError):
                recipe = dict(caps()["recipes"][0])
                if category is None:
                    recipe.pop("category")
                else:
                    recipe["category"] = category
                validate_capabilities(
                    dict(caps(), recipes=[recipe]), "nauvis", 120
                )

    def test_recipe_unlock_effects_are_optional_bounded_and_strict(self):
        recipe = dict(caps()["recipes"][0])
        recipe["unlock_technologies"] = [
            {"name": "automation", "researched": True, "enabled": True},
            {"name": "automation-2", "researched": False, "enabled": True},
        ]
        parsed = validate_capabilities(
            dict(caps(), recipes=[recipe]), "nauvis", 120
        )
        self.assertEqual(
            [item["name"] for item in parsed["recipes"][0]["unlock_technologies"]],
            ["automation", "automation-2"],
        )

        for unlocks in (
            [{"name": "automation", "researched": 1, "enabled": True}],
            [{"name": "automation", "researched": False, "enabled": True}] * 2,
            [{"name": "automation", "researched": False, "enabled": True}] * 9,
            [{"name": "automation-2", "researched": False, "enabled": True},
             {"name": "automation", "researched": False, "enabled": True}],
        ):
            with self.subTest(unlocks=unlocks), self.assertRaises(ValueError):
                validate_capabilities(
                    dict(caps(), recipes=[dict(recipe, unlock_technologies=unlocks)]),
                    "nauvis", 120,
                )

    def test_an_empty_unlock_object_is_accepted_as_no_unlock_effect(self):
        """A recipe with no unlock technology is reported as an empty object.

        The Lua adapter reports ``unlock_by_recipe[name] or {}``, so a recipe
        without an unlock technology serialises as an empty JSON **object**
        instead of an empty array. A live Pyanodons run proved that 3,444 of
        the 9,467 observed recipes carry that shape; rejecting them lost the
        whole catalog frame and the dashboard showed no observation at all.
        """
        recipe = dict(caps()["recipes"][0])
        recipe["unlock_technologies"] = {}
        parsed = validate_capabilities(
            dict(caps(), recipes=[recipe]), "nauvis", 120
        )
        self.assertEqual(parsed["recipes"][0]["unlock_technologies"], [])

    def test_a_non_empty_unlock_object_is_still_rejected(self):
        """Only the empty object is accepted; a populated one fails closed."""
        recipe = dict(caps()["recipes"][0])
        recipe["unlock_technologies"] = {"name": "automation"}
        with self.assertRaises(ValueError):
            validate_capabilities(
                dict(caps(), recipes=[recipe]), "nauvis", 120
            )

    def test_a_recipe_without_the_unlock_key_is_still_accepted(self):
        """The unlock field stays optional."""
        recipe = dict(caps()["recipes"][0])
        recipe.pop("unlock_technologies", None)
        parsed = validate_capabilities(
            dict(caps(), recipes=[recipe]), "nauvis", 120
        )
        self.assertNotIn("unlock_technologies", parsed["recipes"][0])

    def test_factorio_21_category_list_and_determinism_marker_are_bounded(self):
        """Factorio 2.1 recipes may declare several categories and a stochastic
        product amount. Both are accepted with strict bounds; unknown fields
        still fail closed."""
        recipe = dict(caps()["recipes"][0])
        recipe["categories"] = ["crafting", "electromagnetics"]
        parsed = validate_capabilities(
            dict(caps(), recipes=[recipe]), "nauvis", 120
        )
        self.assertEqual(
            parsed["recipes"][0]["categories"], ["crafting", "electromagnetics"]
        )

        stochastic = dict(recipe)
        stochastic["products"] = [
            dict(recipe["products"][0], deterministic=False),
        ]
        parsed = validate_capabilities(
            dict(caps(), recipes=[stochastic]), "nauvis", 120
        )
        self.assertIs(parsed["recipes"][0]["products"][0]["deterministic"], False)

        # The category list must agree with the primary category.
        with self.assertRaises(ValueError):
            validate_capabilities(
                dict(caps(), recipes=[dict(recipe, categories=["other"])]),
                "nauvis", 120,
            )
        # An unbounded or duplicated category list is rejected.
        for categories in ([], ["crafting"] * 9, ["crafting", "crafting"], 12):
            with self.subTest(categories=categories), self.assertRaises(ValueError):
                validate_capabilities(
                    dict(caps(), recipes=[dict(recipe, categories=categories)]),
                    "nauvis", 120,
                )
        # A non-boolean determinism marker is rejected.
        with self.assertRaises(ValueError):
            validate_capabilities(
                dict(caps(), recipes=[dict(
                    recipe, products=[dict(recipe["products"][0], deterministic=1)]
                )]),
                "nauvis", 120,
            )
        # An unrelated unknown field still fails closed.
        with self.assertRaises(ValueError):
            validate_capabilities(
                dict(caps(), recipes=[dict(recipe, unexpected="x")]), "nauvis", 120,
            )

    def test_physical_preview_requires_explicit_observed_rates(self):
        data = validate_capabilities(caps(), "nauvis", 120)
        plan = preview_simple_recipe(
            data, "iron-gear-wheel", machine_speed=1, machine_power_kw=100,
            input_rates={"iron-plate": 1}, power_kw=1000, target_rate=5,
        )
        self.assertAlmostEqual(plan.achievable_rate_gps, 0.5)
        self.assertEqual(plan.feasibility_status, "partial")
        self.assertIn("supply-iron-plate", plan.supply_limiting)

    def test_fluid_or_complex_recipe_is_explicitly_unsupported(self):
        p = caps()
        p["enabled_content"] = ["base", "space-age", "quality", "elevated-rails"]
        p["recipes"][0]["simple"] = False
        c = validate_capabilities(p, "nauvis", 120)
        with self.assertRaises(ValueError):
            preview_simple_recipe(
                c, "iron-gear-wheel", machine_speed=1, machine_power_kw=100,
                input_rates={"iron-plate": 100}, power_kw=1000, target_rate=5)


class MachineCompatibilityAndProductionMath(unittest.TestCase):
    """The observed machine catalog decides what can produce a recipe.

    The recipe rows and the machine rows come from the game's own observed
    data. A machine whose speed or energy the game did not expose is kept
    with that value **unknown**, and it is not a plannable option, because
    a rate cannot be computed from an unknown speed. A value that IS
    present but invalid is refused. A crafting category that no observed
    machine declares has no machine at all. Nothing here is a default.
    """

    def machine(self, name, categories, speed, watts, slots=None):
        row = {"name": name, "crafting_categories": categories,
               "crafting_speed": speed, "energy_usage": watts}
        if slots is not None:
            row["module_slots"] = slots
        return row

    def recipe(self, name, category, seconds, ingredients, products):
        return {"name": name, "enabled": True, "hidden": False, "simple": True,
                "category": category, "categories": [category],
                "crafting_time": seconds, "ingredients": ingredients,
                "products": products}

    def catalog(self, machines=None, recipes=None):
        base = caps()
        base["machines"] = machines if machines is not None else [
            self.machine("assembling-machine-1", ["crafting"], 0.75, 75000, 2),
            self.machine("stone-furnace", ["smelting"], 1.0, 90000),
        ]
        base["recipes"] = recipes if recipes is not None else [
            self.recipe("iron-gear-wheel", "crafting", 0.5,
                        [{"name": "iron-plate", "type": "item", "amount": 2}],
                        [{"name": "iron-gear-wheel", "type": "item", "amount": 1}]),
        ]
        return base

    def test_the_observed_machine_report_is_validated(self):
        parsed = validate_capabilities(self.catalog(), "nauvis", 120)
        self.assertEqual([m["name"] for m in parsed["machines"]],
                         ["assembling-machine-1", "stone-furnace"])
        self.assertEqual(parsed["machines"][0]["crafting_speed"], 0.75)
        self.assertEqual(parsed["machines"][0]["energy_usage"], 75000)

    def test_a_machine_without_an_observed_speed_is_kept_with_an_unknown_speed(self):
        """A speed the game did not report is unknown, not invalid.

        Factorio 2.1.23 exposes the crafting speed on the runtime prototype
        through the METHOD ``get_crafting_speed(quality?)``. A prototype
        that does not declare that method carries no speed at all, and the
        machine is kept with an unknown speed so the planner can still see
        it; the planner then refuses to plan it.
        """
        parsed = validate_capabilities(
            self.catalog([self.machine("m", ["crafting"], None, 1000)]),
            "nauvis", 120)
        self.assertEqual([m["name"] for m in parsed["machines"]], ["m"])
        self.assertIsNone(parsed["machines"][0]["crafting_speed"])

    def test_an_invalid_machine_speed_is_still_refused(self):
        """A speed that IS present must still be a positive number."""
        for speed in (0, -1, "fast"):
            with self.subTest(speed=speed):
                with self.assertRaises(ValueError):
                    validate_capabilities(
                        self.catalog([self.machine("m", ["crafting"], speed, 1000)]),
                        "nauvis", 120)

    def test_a_machine_without_observed_energy_is_kept_with_an_unknown_energy(self):
        """An energy the game did not report is unknown, not invalid."""
        parsed = validate_capabilities(
            self.catalog([self.machine("m", ["crafting"], 1.0, None)]),
            "nauvis", 120)
        self.assertEqual([m["name"] for m in parsed["machines"]], ["m"])
        self.assertIsNone(parsed["machines"][0]["energy_usage"])

    def test_an_invalid_machine_energy_is_still_refused(self):
        """An energy that IS present must still be a positive number."""
        for watts in (0, -1, "150kW"):
            with self.subTest(watts=watts):
                with self.assertRaises(ValueError):
                    validate_capabilities(
                        self.catalog([self.machine("m", ["crafting"], 1.0, watts)]),
                        "nauvis", 120)

    def test_a_machine_with_an_unknown_speed_is_not_a_plannable_option(self):
        """A machine without an observed speed cannot carry a rate.

        It must be excluded from the machine options instead of being
        planned with an invented speed.
        """
        parsed = validate_capabilities(
            self.catalog([self.machine("m", ["crafting"], None, 1000)]),
            "nauvis", 120)
        self.assertEqual(machine_options(parsed["recipes"], parsed["machines"],
                                        "crafting"), [])

    def test_the_observed_quality_information_is_kept(self):
        """The quality-dependent speed and slot information is kept.

        Factorio 2.1.23 declares ``crafting_speed_quality_multiplier`` as a
        dictionary of ``QualityID`` to a double and
        ``quality_affects_module_slots`` as a boolean. Both are observed
        values and are carried through unchanged.
        """
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000, 2)
        machine["quality_affects_module_slots"] = True
        machine["crafting_speed_quality_multiplier"] = {
            "normal": 1.0, "uncommon": 1.5}
        parsed = validate_capabilities(
            self.catalog([machine]), "nauvis", 120)
        row = parsed["machines"][0]
        self.assertTrue(row["quality_affects_module_slots"])
        self.assertEqual(row["crafting_speed_quality_multiplier"],
                         {"normal": 1.0, "uncommon": 1.5})

    def test_the_quality_multipliers_reach_the_plannable_options(self):
        """A plannable machine keeps its observed quality multipliers."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000, 2)
        machine["crafting_speed_quality_multiplier"] = {"normal": 1.0}
        machine["quality_affects_module_slots"] = True
        parsed = validate_capabilities(
            self.catalog([machine]), "nauvis", 120)
        options = machine_options(parsed["recipes"], parsed["machines"], "crafting")
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["crafting_speed_quality_multiplier"],
                         {"normal": 1.0})
        self.assertTrue(options[0]["quality_affects_module_slots"])

    def test_an_invalid_quality_multiplier_is_still_refused(self):
        """A multiplier that IS present must be a finite non-negative number."""
        for factor in (-1, "fast", float("nan"), float("inf")):
            with self.subTest(factor=factor):
                machine = self.machine("m", ["crafting"], 1.0, 1000)
                machine["crafting_speed_quality_multiplier"] = {"normal": factor}
                with self.assertRaises(ValueError):
                    validate_capabilities(
                        self.catalog([machine]), "nauvis", 120)

    def test_an_invalid_quality_slot_flag_is_still_refused(self):
        """The slot flag must be a real boolean."""
        machine = self.machine("m", ["crafting"], 1.0, 1000)
        machine["quality_affects_module_slots"] = "yes"
        with self.assertRaises(ValueError):
            validate_capabilities(self.catalog([machine]), "nauvis", 120)

    def test_a_machine_without_quality_information_keeps_none_of_it(self):
        """A machine that declares no quality information is not padded.

        The absent fields stay absent, so an unknown quality rule is never
        mistaken for a ``False`` or a ``1.0`` multiplier.
        """
        parsed = validate_capabilities(
            self.catalog([self.machine("m", ["crafting"], 1.0, 1000)]),
            "nauvis", 120)
        row = parsed["machines"][0]
        self.assertNotIn("quality_affects_module_slots", row)
        self.assertNotIn("crafting_speed_quality_multiplier", row)

    def test_an_unbounded_or_duplicate_machine_report_is_refused(self):
        for report in ("not-a-list", [{"name": "a", "crafting_categories": ["c"],
                                       "crafting_speed": 1, "energy_usage": 1,
                                       "unknown": 1}]):
            with self.subTest(report=report):
                with self.assertRaises(ValueError):
                    validate_capabilities(
                        dict(self.catalog(), machines=report), "nauvis", 120)
        duplicate = [self.machine("m", ["crafting"], 1.0, 1000),
                     self.machine("m", ["crafting"], 1.0, 1000)]
        with self.assertRaises(ValueError):
            validate_capabilities(self.catalog(duplicate), "nauvis", 120)

    def test_only_machines_that_declare_the_category_are_offered(self):
        parsed = validate_capabilities(self.catalog(), "nauvis", 120)
        options = machine_options(parsed["recipes"], parsed["machines"], "crafting")
        self.assertEqual([o["name"] for o in options], ["assembling-machine-1"])
        self.assertEqual(machine_options(
            parsed["recipes"], parsed["machines"], "nano"), [])

    def test_a_modded_machine_with_its_own_category_is_offered(self):
        machines = [self.machine("py-nano-fabricator", ["nano"], 1.5, 90000)]
        parsed = validate_capabilities(self.catalog(machines), "nauvis", 120)
        options = machine_options(parsed["recipes"], parsed["machines"], "nano")
        self.assertEqual(options[0]["name"], "py-nano-fabricator")
        self.assertEqual(options[0]["crafting_speed"], 1.5)

    # -- the observed module, fluid-box and quality rules ------------------

    def test_the_allowed_effects_are_accepted_and_preserved(self):
        """Factorio 2.1.23 declares ``allowed_effects`` on a crafting machine.

        It is an ``EffectTypeLimitation``: the effects a module or a beacon
        may apply to this machine. The rule decides whether a module is
        legal here, so it must reach the planner.
        """
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["allowed_effects"] = ["speed", "productivity"]
        parsed = validate_capabilities(self.catalog([machine]), "nauvis", 120)
        self.assertEqual(parsed["machines"][0]["allowed_effects"],
                         ["productivity", "speed"])

    def test_a_single_allowed_effect_is_accepted(self):
        """``EffectTypeLimitation`` may be one literal rather than a list."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["allowed_effects"] = "speed"
        parsed = validate_capabilities(self.catalog([machine]), "nauvis", 120)
        self.assertEqual(parsed["machines"][0]["allowed_effects"], ["speed"])

    def test_an_empty_allowed_effect_list_means_no_module_is_legal(self):
        """The 2.1.23 API states that an empty list forbids modules entirely."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["allowed_effects"] = []
        parsed = validate_capabilities(self.catalog([machine]), "nauvis", 120)
        self.assertEqual(parsed["machines"][0]["allowed_effects"], [])

    def test_an_unknown_effect_name_is_refused(self):
        """Only the five declared 2.1.23 effect literals are accepted."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["allowed_effects"] = ["speed", "teleportation"]
        with self.assertRaises(ValueError):
            validate_capabilities(self.catalog([machine]), "nauvis", 120)

    def test_the_allowed_module_categories_are_accepted_verbatim(self):
        """A mod may add its own module category, so the name is kept."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["allowed_module_categories"] = ["speed", "py-special"]
        parsed = validate_capabilities(self.catalog([machine]), "nauvis", 120)
        self.assertEqual(parsed["machines"][0]["allowed_module_categories"],
                         ["py-special", "speed"])

    def test_the_observed_fluid_box_is_accepted_and_preserved(self):
        """Factorio 2.1.23 ``FluidBox`` declares ``production_type``,
        ``filter`` and ``volume``.

        The earlier adapter read ``filter_type`` and ``fluid_box_index``,
        which the API does not declare, so the reported filter was always
        the fallback "item". The declared fields must be read instead.
        """
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["fluid_boxes"] = [
            {"production_type": "input", "filter": "water", "volume": 200},
        ]
        parsed = validate_capabilities(self.catalog([machine]), "nauvis", 120)
        box = parsed["machines"][0]["fluid_boxes"][0]
        self.assertEqual(box["production_type"], "input")
        self.assertEqual(box["filter"], "water")
        self.assertEqual(box["volume"], 200)

    def test_an_unknown_fluid_box_field_is_refused(self):
        """The 2.1.23 fluid box declares no ``filter_type`` field."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["fluid_boxes"] = [{"filter_type": "item"}]
        with self.assertRaises(ValueError):
            validate_capabilities(self.catalog([machine]), "nauvis", 120)

    def test_an_unknown_fluid_box_production_type_is_refused(self):
        """``ProductionType`` is a closed literal union in 2.1.23."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["fluid_boxes"] = [{"production_type": "sideways"}]
        with self.assertRaises(ValueError):
            validate_capabilities(self.catalog([machine]), "nauvis", 120)

    def test_an_unknown_machine_field_is_refused(self):
        """A field the backend never reports must not be accepted."""
        machine = self.machine("assembling-machine-1", ["crafting"], 0.75, 75000)
        machine["quality_multiplier"] = 1.5
        with self.assertRaises(ValueError):
            validate_capabilities(self.catalog([machine]), "nauvis", 120)

    def test_the_production_math_reports_rates_counts_and_power(self):
        parsed = validate_capabilities(self.catalog(), "nauvis", 120)
        plan = plan_recipe_production(parsed, "iron-gear-wheel",
                                      target_per_second=1.0)
        self.assertEqual(plan["status"], "ok")
        row = plan["machines"][0]
        # 0.75 speed / 0.5 s = 1.5 crafts/s, one gear each.
        self.assertAlmostEqual(row["crafts_per_second"], 1.5)
        self.assertAlmostEqual(row["items_per_second"], 1.5)
        self.assertAlmostEqual(row["items_per_minute"], 90.0)
        self.assertEqual(row["machines_needed"], 1)
        # Two plates per craft.
        self.assertAlmostEqual(row["ingredients_per_second"]["item:iron-plate"], 3.0)
        self.assertAlmostEqual(row["ingredients_per_minute"]["item:iron-plate"], 180.0)
        # 75 kW working draw for one machine.
        self.assertAlmostEqual(row["energy_kw"], 75.0)

    def test_the_machine_count_rounds_up_to_a_whole_machine(self):
        parsed = validate_capabilities(self.catalog(), "nauvis", 120)
        plan = plan_recipe_production(parsed, "iron-gear-wheel",
                                      target_per_second=1.3)
        row = plan["machines"][0]
        self.assertEqual(row["machines_needed"], 1)
        plan = plan_recipe_production(parsed, "iron-gear-wheel",
                                      target_per_second=1.6)
        row = plan["machines"][0]
        self.assertEqual(row["machines_needed"], 2)
        self.assertAlmostEqual(row["energy_kw"], 150.0)

    def test_a_category_without_an_observed_machine_is_unresolved(self):
        # The recipe runs in a category that no observed machine declares.
        recipes = [self.recipe(
            "nano-alloy", "nano", 2.0,
            [{"name": "silver-plate", "type": "item", "amount": 4}],
            [{"name": "nano-alloy", "type": "item", "amount": 1}])]
        parsed = validate_capabilities(
            self.catalog([self.machine("assembling-machine-1", ["crafting"],
                                       0.75, 75000)], recipes=recipes),
            "nauvis", 120)
        plan = plan_recipe_production(parsed, "nano-alloy",
                                      target_per_second=1.0)
        self.assertEqual(plan["status"], "unresolved")
        self.assertIn("No observed machine", plan["reason"])

    def test_a_multi_output_recipe_is_refused(self):
        recipes = [self.recipe(
            "oil-processing", "chemistry", 5.0,
            [{"name": "crude-oil", "type": "fluid", "amount": 100}],
            [{"name": "heavy-oil", "type": "fluid", "amount": 25},
             {"name": "light-oil", "type": "fluid", "amount": 45}])]
        parsed = validate_capabilities(
            self.catalog(recipes=recipes), "nauvis", 120)
        with self.assertRaises(ValueError):
            plan_recipe_production(parsed, "oil-processing",
                                   target_per_second=1.0)

    def test_a_stochastic_yield_is_refused(self):
        recipes = [self.recipe(
            "lucky-recipe", "crafting", 1.0,
            [{"name": "iron-plate", "type": "item", "amount": 1}],
            [{"name": "iron-gear-wheel", "type": "item", "amount": 1,
              "deterministic": False}])]
        parsed = validate_capabilities(
            self.catalog(recipes=recipes), "nauvis", 120)
        with self.assertRaises(ValueError):
            plan_recipe_production(parsed, "lucky-recipe", target_per_second=1.0)

    def test_a_module_speed_bonus_changes_the_effective_speed(self):
        parsed = validate_capabilities(self.catalog(), "nauvis", 120)
        plan = plan_recipe_production(parsed, "iron-gear-wheel",
                                      target_per_second=1.0,
                                      module_speed_bonus=0.2)
        row = plan["machines"][0]
        self.assertAlmostEqual(row["effective_speed"], 0.9)
        self.assertAlmostEqual(row["items_per_second"], 1.8)

    def test_an_unknown_recipe_is_refused(self):
        parsed = validate_capabilities(self.catalog(), "nauvis", 120)
        with self.assertRaises(ValueError):
            plan_recipe_production(parsed, "not-in-the-catalog",
                                   target_per_second=1.0)


class LegacyExecutorSafety(unittest.IsolatedAsyncioTestCase):
    async def test_execute_fails_before_any_mcp_or_gameplay_call(self):
        with patch("safe_executor.mcp_parameters") as parameters:
            with self.assertRaisesRegex(PermissionError, "Legacy --execute disabled"):
                await legacy_executor_main(True)
            parameters.assert_not_called()


class StochasticProductionMath(unittest.TestCase):
    """A random yield is never presented as a deterministic one.

    The three quantities that are easily confused are kept apart:

    * the **guaranteed** output, which happens on every craft;
    * the **expected** output, the long-run average, which is only reported
      when the observed probability justifies it; and
    * the **bounds**, which are always kept for a ranged or probabilistic
      output.

    Factorio 2.1.23 declares ``independent_probability`` as a per-craft
    probability and ``extra_count_fraction`` as the probability of one
    extra unit, so ``probability * amount`` is a real expectation. A
    product whose amount is a *range* has no verified distribution inside
    the range, so its expectation stays unknown rather than being guessed
    as the midpoint.
    """

    def machine(self, name="assembling-machine-1", categories=("crafting",),
                speed=0.75, watts=75000):
        return {"name": name, "crafting_categories": list(categories),
                "crafting_speed": speed, "energy_usage": watts}

    def recipe(self, name, products, ingredients=(), seconds=0.5,
               category="crafting"):
        return {"name": name, "enabled": True, "hidden": False, "simple": False,
                "category": category, "categories": [category],
                "crafting_time": seconds, "ingredients": list(ingredients),
                "products": list(products)}

    def catalog(self, recipes, machines=None):
        base = caps()
        base["machines"] = machines if machines is not None else [self.machine()]
        base["recipes"] = list(recipes)
        return base

    def plan(self, recipes, target=1.0, **kwargs):
        parsed = validate_capabilities(self.catalog(recipes), "nauvis", 120)
        return plan_stochastic_recipe(parsed, recipes[0]["name"],
                                      target_per_second=target, **kwargs)

    # -- the deterministic case -------------------------------------------

    def test_a_deterministic_recipe_reports_a_guaranteed_rate(self):
        recipes = [self.recipe("plate", [
            {"name": "iron-plate", "type": "item", "amount": 1}])]
        plan = self.plan(recipes)
        self.assertEqual(plan["status"], "ok")
        row = plan["machines"][0]
        # 0.75 speed / 0.5 s = 1.5 crafts/s, one plate each.
        self.assertAlmostEqual(row["guaranteed_per_second"], 1.5)
        self.assertAlmostEqual(row["expected_per_second"], 1.5)
        self.assertEqual(row["machines_needed_basis"], "guaranteed")

    # -- the probabilistic case -------------------------------------------

    def test_a_probabilistic_product_has_no_guaranteed_rate(self):
        """A product that may not appear is never guaranteed."""
        recipes = [self.recipe("ore", [
            {"name": "iron-ore", "type": "item", "amount": 1,
             "independent_probability": 0.25}])]
        plan = self.plan(recipes)
        row = plan["machines"][0]
        self.assertIsNone(row["guaranteed_per_second"])
        self.assertIsNotNone(row["expected_per_second"])
        self.assertEqual(row["machines_needed_basis"], "expected")

    def test_a_probabilistic_product_reports_the_justified_expectation(self):
        """``probability * amount`` is the real expectation of a 2.1.23
        ``independent_probability``."""
        recipes = [self.recipe("ore", [
            {"name": "iron-ore", "type": "item", "amount": 1,
             "independent_probability": 0.25}])]
        row = self.plan(recipes)["machines"][0]
        # 1.5 crafts/s * (0.25 * 1) = 0.375 expected items/s.
        self.assertAlmostEqual(row["expected_per_second"], 0.375)

    def test_a_probabilistic_product_reports_its_bounds(self):
        """The lower bound is zero, because the product may not appear."""
        recipes = [self.recipe("ore", [
            {"name": "iron-ore", "type": "item", "amount": 1,
             "independent_probability": 0.25}])]
        row = self.plan(recipes)["machines"][0]
        self.assertAlmostEqual(row["minimum_per_second"], 0.0)
        self.assertAlmostEqual(row["maximum_per_second"], 1.5)

    def test_a_probabilistic_product_records_why_it_is_uncertain(self):
        recipes = [self.recipe("ore", [
            {"name": "iron-ore", "type": "item", "amount": 1,
             "independent_probability": 0.25}])]
        row = self.plan(recipes)["machines"][0]
        reasons = row["products"][0]["reasons"]
        self.assertTrue(any("probability" in reason for reason in reasons))

    # -- the ranged case --------------------------------------------------

    def test_a_ranged_product_has_no_expected_rate(self):
        """The distribution inside a range is not verified, so no midpoint."""
        recipes = [self.recipe("ore", [
            {"name": "iron-ore", "type": "item", "amount": 1,
             "amount_min": 1, "amount_max": 3}])]
        row = self.plan(recipes)["machines"][0]
        self.assertIsNone(row["guaranteed_per_second"])
        self.assertIsNone(row["expected_per_second"])
        self.assertAlmostEqual(row["minimum_per_second"], 1.5)
        self.assertAlmostEqual(row["maximum_per_second"], 4.5)

    # -- byproducts --------------------------------------------------------

    def test_a_byproduct_is_reported_separately_from_the_main_product(self):
        recipes = [self.recipe("refined", [
            {"name": "refined-plate", "type": "item", "amount": 1},
            {"name": "iron-ore", "type": "item", "amount": 2}])]
        row = self.plan(recipes)["machines"][0]
        self.assertEqual(len(row["byproducts"]), 1)
        self.assertEqual(row["byproducts"][0]["name"], "iron-ore")
        self.assertTrue(row["byproducts"][0]["is_byproduct"])
        self.assertAlmostEqual(row["byproducts"][0]["guaranteed_per_second"], 3.0)

    def test_a_probabilistic_byproduct_is_not_a_guaranteed_byproduct(self):
        recipes = [self.recipe("refined", [
            {"name": "refined-plate", "type": "item", "amount": 1},
            {"name": "iron-ore", "type": "item", "amount": 2,
             "independent_probability": 0.5}])]
        row = self.plan(recipes)["machines"][0]
        byproduct = row["byproducts"][0]
        self.assertIsNone(byproduct["guaranteed_per_second"])
        self.assertAlmostEqual(byproduct["expected_per_second"], 1.5)

    # -- productivity ------------------------------------------------------

    def test_productivity_scales_a_normal_product(self):
        recipes = [self.recipe("plate", [
            {"name": "iron-plate", "type": "item", "amount": 1}])]
        row = self.plan(recipes, productivity_bonus=0.5)["machines"][0]
        self.assertAlmostEqual(row["guaranteed_per_second"], 1.5 * 1.5)

    def test_a_productivity_restricted_product_is_not_scaled_fully(self):
        """``ignored_by_productivity`` is the amount deducted from the bonus
        craft, so the bonus does not apply to it in full."""
        recipes = [self.recipe("plate", [
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_productivity": 1}])]
        row = self.plan(recipes, productivity_bonus=0.5)["machines"][0]
        # The bonus craft adds 0.5 units and one unit is deducted, so the
        # surviving factor is 1.0 and the rate is unchanged.
        self.assertAlmostEqual(row["guaranteed_per_second"], 1.5)

    # -- the unresolved cases ----------------------------------------------

    def test_a_recipe_without_an_observed_machine_is_unresolved(self):
        recipes = [self.recipe("plate", [
            {"name": "iron-plate", "type": "item", "amount": 1}],
            category="nano")]
        plan = self.plan(recipes)
        self.assertEqual(plan["status"], "unresolved")
        self.assertIn("No observed machine", plan["reason"])

    def test_a_disabled_recipe_is_refused(self):
        recipes = [self.recipe("plate", [
            {"name": "iron-plate", "type": "item", "amount": 1}])]
        recipes[0]["enabled"] = False
        with self.assertRaises(ValueError):
            self.plan(recipes)


class BlueprintPlanningModel(unittest.TestCase):
    """The blueprint model answers the questions a blueprint needs.

    It reads only the observed catalog and the observed machines, and it
    never places a blueprint or writes to the game. A probabilistic output
    stays probabilistic all the way through the model.
    """

    def machine(self, name, categories=("crafting",), speed=0.75, watts=75000,
                **extra):
        row = {"name": name, "crafting_categories": list(categories),
               "crafting_speed": speed, "energy_usage": watts}
        row.update(extra)
        return row

    def recipe(self, name, products, ingredients=(), seconds=0.5,
               category="crafting", technologies=None):
        return {"name": name, "enabled": True, "hidden": False, "simple": False,
                "category": category, "categories": [category],
                "crafting_time": seconds, "ingredients": list(ingredients),
                "products": list(products),
                "unlock_technologies": technologies or []}

    def catalog(self, recipes, machines):
        base = caps()
        base["machines"] = list(machines)
        base["recipes"] = list(recipes)
        return base

    def plan(self, recipes, machines, name="gear", target=1.0, **kwargs):
        parsed = validate_capabilities(self.catalog(recipes, machines),
                                       "nauvis", 120)
        return plan_blueprint(parsed, name, target_per_second=target, **kwargs)

    def test_the_verified_speed_drives_the_whole_rate_calculation(self):
        """A verified machine speed drives every rate the plan reports.

        This is the end-to-end link between the recovered prototype API
        and the production mathematics: the speed the adapter now reads
        through ``get_crafting_speed`` sets the crafts per second, the
        output rate, the machine count, the ingredient throughput and the
        power draw. No value is invented anywhere in the chain.
        """
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}],
            ingredients=[{"name": "plate", "type": "item", "amount": 2}])]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        plan = self.plan(recipes, machines, target=1.0)
        self.assertEqual(plan["status"], "ok")
        row = plan["machines"][0]
        # 0.75 speed / 0.5 s = 1.5 crafts/s and one gear per craft.
        self.assertAlmostEqual(row["crafts_per_second"], 1.5)
        self.assertAlmostEqual(row["guaranteed_per_second"], 1.5)
        self.assertAlmostEqual(row["expected_per_second"], 1.5)
        # One machine at 1.5/s reaches the 1/s target.
        self.assertEqual(row["machines_needed"], 1)
        self.assertEqual(row["machines_needed_basis"], "guaranteed")
        # Two plates per craft at 1.5 crafts/s.
        self.assertAlmostEqual(row["ingredients_per_second"]["item:plate"], 3.0)
        self.assertAlmostEqual(row["ingredients_per_minute"]["item:plate"], 180.0)
        # The machine draws 75 kW and one is needed.
        self.assertAlmostEqual(row["energy_kw"], 75.0)
        # The observed speed is the one that was used.
        self.assertAlmostEqual(row["crafting_speed"], 0.75)
        self.assertAlmostEqual(row["effective_speed"], 0.75)

    def test_a_higher_verified_speed_needs_fewer_machines(self):
        """The machine count follows the observed speed, not a default."""
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}])]
        slow = self.plan(recipes, [self.machine("m", speed=0.75)], target=1.0)
        fast = self.plan(recipes, [self.machine("m", speed=1.5)], target=1.0)
        self.assertEqual(slow["machines"][0]["machines_needed"], 1)
        self.assertEqual(fast["machines"][0]["machines_needed"], 1)
        # A target above one machine's output needs more of them.
        slow_high = self.plan(recipes, [self.machine("m", speed=0.75)],
                               target=2.0)
        fast_high = self.plan(recipes, [self.machine("m", speed=1.5)],
                               target=2.0)
        self.assertEqual(slow_high["machines"][0]["machines_needed"], 2)
        self.assertEqual(fast_high["machines"][0]["machines_needed"], 1)

    def test_the_plan_reports_the_machines_that_can_craft_the_recipe(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}],
            ingredients=[{"name": "plate", "type": "item", "amount": 2}])]
        machines = [
            self.machine("assembling-machine-1", speed=0.75),
            self.machine("assembling-machine-2", speed=1.25),
            self.machine("stone-furnace", categories=("smelting",), speed=1.0),
        ]
        plan = self.plan(recipes, machines)
        self.assertEqual(plan["status"], "ok")
        offered = [row["machine"] for row in plan["machines"]]
        self.assertEqual(offered, ["assembling-machine-1", "assembling-machine-2"])

    def test_the_plan_reports_the_machine_count_and_the_power(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}])]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        plan = self.plan(recipes, machines, target=1.0)
        row = plan["machines"][0]
        # 0.75 speed / 0.5 s = 1.5 crafts/s, so one machine reaches 1/s.
        self.assertEqual(row["machines_needed"], 1)
        self.assertAlmostEqual(row["energy_kw"], 75.0)
        self.assertEqual(row["machines_needed_basis"], "guaranteed")

    def test_the_plan_reports_the_input_throughput(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}],
            ingredients=[{"name": "plate", "type": "item", "amount": 2}])]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        plan = self.plan(recipes, machines)
        row = plan["machines"][0]
        # Two plates per craft at 1.5 crafts/s.
        self.assertAlmostEqual(row["ingredients_per_second"]["item:plate"], 3.0)
        self.assertAlmostEqual(row["ingredients_per_minute"]["item:plate"], 180.0)

    def test_the_plan_reports_the_byproducts_for_routing(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1},
            {"name": "scrap", "type": "item", "amount": 2}])]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        plan = self.plan(recipes, machines)
        byproducts = plan["machines"][0]["byproducts"]
        self.assertEqual(len(byproducts), 1)
        self.assertEqual(byproducts[0]["name"], "scrap")
        self.assertAlmostEqual(byproducts[0]["guaranteed_per_second"], 3.0)

    def test_the_plan_keeps_a_probabilistic_output_probabilistic(self):
        recipes = [self.recipe("ore", [
            {"name": "ore", "type": "item", "amount": 1,
             "independent_probability": 0.25}])]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        plan = self.plan(recipes, machines, name="ore")
        row = plan["machines"][0]
        self.assertIsNone(row["guaranteed_per_second"])
        self.assertAlmostEqual(row["expected_per_second"], 0.375)

    def test_the_plan_reports_the_unlock_technologies(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}],
            technologies=[{"name": "assembly-line", "researched": False,
                           "enabled": True},
                          {"name": "automation", "researched": True,
                           "enabled": True}])]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        plan = self.plan(recipes, machines)
        self.assertEqual(
            [tech["name"] for tech in plan["technologies"]],
            ["assembly-line", "automation"])
        self.assertFalse(plan["technologies"][0]["researched"])
        self.assertTrue(plan["technologies"][1]["researched"])

    def test_the_plan_reports_the_module_rules_of_the_machine(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}])]
        machines = [self.machine(
            "assembling-machine-1", speed=0.75, module_slots=2,
            allowed_effects=["speed", "productivity"],
            allowed_module_categories=["speed"])]
        plan = self.plan(recipes, machines)
        row = plan["machines"][0]
        self.assertEqual(row["module_slots"], 2)
        self.assertEqual(row["allowed_effects"], ["productivity", "speed"])
        self.assertEqual(row["allowed_module_categories"], ["speed"])

    def test_the_plan_offers_every_observed_machine_as_an_alternative(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}])]
        machines = [
            self.machine("assembling-machine-1", speed=0.75, watts=75000),
            self.machine("assembling-machine-2", speed=1.25, watts=90000),
        ]
        plan = self.plan(recipes, machines)
        self.assertEqual(len(plan["machines"]), 2)
        self.assertIn(plan["recommended_machine"],
                      {"assembling-machine-1", "assembling-machine-2"})

    def test_the_plan_is_unresolved_without_an_observed_machine(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}], category="nano")]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        plan = self.plan(recipes, machines)
        self.assertEqual(plan["status"], "unresolved")
        self.assertIn("No observed machine", plan["reason"])

    def test_the_plan_refuses_a_recipe_outside_the_observed_catalog(self):
        recipes = [self.recipe("gear", [
            {"name": "gear", "type": "item", "amount": 1}])]
        machines = [self.machine("assembling-machine-1", speed=0.75)]
        with self.assertRaises(ValueError):
            self.plan(recipes, machines, name="not-in-the-catalog")


class LargeResearchCatalogTests(unittest.TestCase):
    def test_large_observed_research_set_and_hard_overflow_bound(self):
        raw = caps()
        raw["research"] = [f"technology-{i}" for i in range(2000)]
        checked = validate_capabilities(raw, "nauvis", 120)
        self.assertEqual(len(checked["research"]), 2000)
        raw["research"] = [f"technology-{i}" for i in range(16385)]
        with self.assertRaises(ValueError):
            validate_capabilities(raw, "nauvis", 120)
