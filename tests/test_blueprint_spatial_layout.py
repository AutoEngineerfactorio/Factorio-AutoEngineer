"""R08-A: spatial layout tests for the connected-blueprint increment.

The positive cases use SYNTHETIC observed records that carry the same
fields the game reports. They are not Pyanodons or vanilla prototype data
and they are not gameplay certification: they prove that the planner
derives its geometry and its flow plan from the observation it was given.
"""
import unittest

from agent.blueprint_spatial_layout import (
    DRAFT_STATUS,
    LayoutError,
    assert_layout_valid,
    layout_is_complete,
    observed_footprint,
    plan_from_observations,
    plan_layout,
    summarize,
    validate_layout,
)


def observed_machine(name="assembler-1", width=3, height=3, direction=0,
                     **extra):
    """Return one synthetic observed machine record."""
    record = {
        "name": name,
        "size": {"width": width, "height": height},
        "direction": direction,
        "crafting_speed": 1.0,
        "energy_usage": 90000.0,
    }
    record.update(extra)
    return record


def observed_recipe(name="iron-plate", ingredients=None, products=None,
                    crafting_time=3.2):
    """Return one synthetic observed recipe record."""
    return {
        "name": name,
        "category": "crafting",
        "crafting_time": crafting_time,
        "ingredients": ingredients if ingredients is not None else [
            {"name": "iron-ore", "amount": 1.0, "type": "item"},
        ],
        "products": products if products is not None else [
            {"name": "iron-plate", "amount": 1.0, "type": "item"},
        ],
    }


class FootprintTests(unittest.TestCase):
    def test_observed_size_becomes_the_footprint(self):
        footprint = observed_footprint(observed_machine(width=3, height=3))
        self.assertEqual((footprint.width, footprint.height), (3, 3))
        self.assertEqual(footprint.tiles, 9)

    def test_south_direction_swaps_the_footprint_axes(self):
        footprint = observed_footprint(observed_machine(width=4, height=2,
                                                       direction=4))
        self.assertEqual((footprint.width, footprint.height), (2, 4))

    def test_west_direction_swaps_the_footprint_axes(self):
        footprint = observed_footprint(observed_machine(width=4, height=2,
                                                       direction=6))
        self.assertEqual((footprint.width, footprint.height), (2, 4))

    def test_east_direction_keeps_the_footprint_axes(self):
        footprint = observed_footprint(observed_machine(width=4, height=2,
                                                       direction=2))
        self.assertEqual((footprint.width, footprint.height), (4, 2))

    def test_machine_without_observed_size_is_refused(self):
        with self.assertRaises(LayoutError):
            observed_footprint({"name": "assembler-1"})

    def test_machine_with_a_non_numeric_size_is_refused(self):
        with self.assertRaises(LayoutError):
            observed_footprint({"name": "assembler-1",
                                "size": {"width": "3", "height": 3}})

    def test_machine_with_an_unsupported_size_field_is_refused(self):
        with self.assertRaises(LayoutError):
            observed_footprint({"name": "assembler-1",
                                "size": {"width": 3, "height": 3, "depth": 1}})

    def test_machine_with_an_invalid_direction_is_refused(self):
        with self.assertRaises(LayoutError):
            observed_footprint(observed_machine(direction=9))

    def test_oversized_footprint_is_refused(self):
        with self.assertRaises(LayoutError):
            observed_footprint(observed_machine(width=40, height=40))


class LayoutTests(unittest.TestCase):
    def test_machines_do_not_overlap(self):
        layout = plan_layout(
            observed_recipe(), observed_machine(width=3, height=3),
            machine_count=7, columns=3)
        tiles = set()
        for placement in layout.placements:
            self.assertFalse(tiles & placement.occupied_tiles)
            tiles |= placement.occupied_tiles
        self.assertEqual(len(tiles), 7 * 9)

    def test_layout_is_validated_independently(self):
        layout = plan_layout(
            observed_recipe(), observed_machine(), machine_count=4, columns=2)
        self.assertEqual(validate_layout(layout), [])
        self.assertTrue(layout_is_complete(layout))

    def test_ingredient_delivery_comes_from_the_observed_recipe(self):
        layout = plan_layout(
            observed_recipe(ingredients=[
                {"name": "iron-ore", "amount": 1.0, "type": "item"},
                {"name": "water", "amount": 10.0, "type": "fluid"},
            ]),
            observed_machine(), machine_count=1)
        self.assertEqual([c.item for c in layout.inputs], ["iron-ore", "water"])
        self.assertFalse(layout.inputs[0].fluid)
        self.assertTrue(layout.inputs[1].fluid)

    def test_product_output_comes_from_the_observed_recipe(self):
        layout = plan_layout(
            observed_recipe(products=[
                {"name": "iron-plate", "amount": 2.0, "type": "item"},
            ]),
            observed_machine(), machine_count=1)
        self.assertEqual([c.item for c in layout.outputs], ["iron-plate"])
        # One craft per 3.2 s at speed 1 is 18.75 crafts/min, 2 plates each.
        self.assertAlmostEqual(layout.outputs[0].amount_per_minute, 37.5)

    def test_flow_scales_with_the_machine_count(self):
        single = plan_layout(
            observed_recipe(), observed_machine(), machine_count=1)
        triple = plan_layout(
            observed_recipe(), observed_machine(), machine_count=3)
        self.assertAlmostEqual(
            triple.inputs[0].amount_per_minute,
            single.inputs[0].amount_per_minute * 3)

    def test_power_demand_uses_the_observed_energy_usage(self):
        layout = plan_layout(
            observed_recipe(), observed_machine(energy_usage=90000.0),
            machine_count=4)
        self.assertAlmostEqual(layout.power_watts, 360000.0)

    def test_layout_is_labelled_a_draft(self):
        layout = plan_layout(
            observed_recipe(), observed_machine(), machine_count=2)
        self.assertEqual(layout.status, DRAFT_STATUS)
        self.assertTrue(any("NOT verified" in w for w in layout.warnings))

    def test_document_carries_the_placement_and_direction(self):
        layout = plan_layout(
            observed_recipe(), observed_machine(direction=4), machine_count=2,
            columns=1)
        document = layout.document(
            label="plate", description="draft", version=(2 << 48) | (1 << 32))
        entities = document["blueprint"]["entities"]
        self.assertEqual(len(entities), 2)
        self.assertEqual(entities[0]["direction"], 4)
        self.assertEqual(entities[0]["recipe"], "iron-plate")

    def test_summary_is_json_safe(self):
        layout = plan_layout(
            observed_recipe(), observed_machine(), machine_count=2)
        report = summarize(layout)
        self.assertEqual(report["machine_count"], 2)
        self.assertEqual(report["problems"], [])


class NegativeLayoutTests(unittest.TestCase):
    """Unsupported or incomplete observations must be refused."""

    def test_recipe_without_observed_ingredients_is_refused(self):
        recipe = observed_recipe()
        del recipe["ingredients"]
        with self.assertRaises(LayoutError):
            plan_layout(recipe, observed_machine(), machine_count=1)

    def test_recipe_without_observed_products_is_refused(self):
        recipe = observed_recipe()
        del recipe["products"]
        with self.assertRaises(LayoutError):
            plan_layout(recipe, observed_machine(), machine_count=1)

    def test_ingredient_row_without_a_name_is_refused(self):
        with self.assertRaises(LayoutError):
            plan_layout(
                observed_recipe(ingredients=[{"amount": 1.0}]),
                observed_machine(), machine_count=1)

    def test_ingredient_row_without_a_positive_amount_is_refused(self):
        with self.assertRaises(LayoutError):
            plan_layout(
                observed_recipe(ingredients=[
                    {"name": "iron-ore", "amount": 0.0}]),
                observed_machine(), machine_count=1)

    def test_machine_without_observed_speed_is_refused(self):
        machine = observed_machine()
        del machine["crafting_speed"]
        with self.assertRaises(LayoutError):
            plan_layout(observed_recipe(), machine, machine_count=1)

    def test_recipe_without_observed_crafting_time_is_refused(self):
        recipe = observed_recipe()
        del recipe["crafting_time"]
        with self.assertRaises(LayoutError):
            plan_layout(recipe, observed_machine(), machine_count=1)

    def test_zero_machine_count_is_refused(self):
        with self.assertRaises(LayoutError):
            plan_layout(observed_recipe(), observed_machine(), machine_count=0)

    def test_excessive_machine_count_is_refused(self):
        with self.assertRaises(LayoutError):
            plan_layout(observed_recipe(), observed_machine(), machine_count=257)

    def test_invalid_column_count_is_refused(self):
        with self.assertRaises(LayoutError):
            plan_layout(observed_recipe(), observed_machine(),
                        machine_count=1, columns=0)

    def test_invalid_gap_is_refused(self):
        with self.assertRaises(LayoutError):
            plan_layout(observed_recipe(), observed_machine(),
                        machine_count=1, gap=-1)


class ObservationSnapshotTests(unittest.TestCase):
    def test_layout_is_planned_from_the_observed_snapshot(self):
        observations = {
            "recipes": [observed_recipe()],
            "machines": [observed_machine()],
        }
        layout = plan_from_observations(
            observations, recipe_name="iron-plate",
            machine_name="assembler-1", machine_count=2)
        self.assertEqual(layout.machine_count, 2)

    def test_missing_recipe_in_the_snapshot_is_refused(self):
        observations = {"recipes": [], "machines": [observed_machine()]}
        with self.assertRaises(LayoutError):
            plan_from_observations(
                observations, recipe_name="iron-plate",
                machine_name="assembler-1", machine_count=1)

    def test_missing_machine_in_the_snapshot_is_refused(self):
        observations = {"recipes": [observed_recipe()], "machines": []}
        with self.assertRaises(LayoutError):
            plan_from_observations(
                observations, recipe_name="iron-plate",
                machine_name="assembler-1", machine_count=1)

    def test_snapshot_without_a_machine_size_is_refused(self):
        machine = observed_machine()
        del machine["size"]
        observations = {"recipes": [observed_recipe()], "machines": [machine]}
        with self.assertRaises(LayoutError):
            plan_from_observations(
                observations, recipe_name="iron-plate",
                machine_name="assembler-1", machine_count=1)

    def test_snapshot_without_a_recipe_list_is_refused(self):
        with self.assertRaises(LayoutError):
            plan_from_observations(
                {"machines": [observed_machine()]},
                recipe_name="iron-plate", machine_name="assembler-1",
                machine_count=1)


class ValidatorTests(unittest.TestCase):
    def test_validator_reports_an_overlap(self):
        layout = plan_layout(
            observed_recipe(), observed_machine(width=3, height=3),
            machine_count=2, columns=1)
        # A one-column layout cannot overlap, so build a broken layout by
        # hand to prove the validator is independent of the planner.
        broken = layout.__class__(
            placements=(
                layout.placements[0],
                layout.placements[0].__class__(
                    entity_number=2, name=layout.placements[0].name,
                    recipe=layout.placements[0].recipe,
                    direction=layout.placements[0].direction,
                    position=layout.placements[0].position,
                    footprint=layout.placements[0].footprint),
            ),
            inputs=layout.inputs, outputs=layout.outputs,
            power_watts=layout.power_watts, status=layout.status)
        problems = validate_layout(broken)
        self.assertTrue(problems)
        with self.assertRaises(LayoutError):
            assert_layout_valid(broken)


if __name__ == "__main__":
    unittest.main()
