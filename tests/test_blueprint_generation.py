"""Observed-recipe generator prevents invented machine compatibility and math."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from blueprint_document import decode
from blueprint_generation import GenerationError, generate_production_blueprint

RECIPE = {
    "name": "iron-gear-wheel", "enabled": True, "hidden": False,
    "category": "crafting", "crafting_time": 0.5,
    "ingredients": [{"name": "iron-plate", "type": "item", "amount": 2}],
    "products": [{"name": "iron-gear-wheel", "type": "item", "amount": 1}],
}
MACHINE = {"name": "assembling-machine-2", "crafting_speed": 0.75,
           "crafting_categories": ["crafting"]}


class ObservedGenerationTests(unittest.TestCase):
    def generate(self, **options):
        return generate_production_blueprint(
            options.get("recipe", RECIPE), options.get("machine", MACHINE),
            options.get("item", "iron-gear-wheel"), options.get("rate", 180),
            source_fingerprint=options.get("fingerprint", "catalog:snapshot"),
            grid_columns=6)

    def test_machine_count_and_ingredients_are_math_grounded(self):
        draft = self.generate()
        self.assertEqual(draft.machine_count, 2)
        self.assertEqual(draft.expected_per_minute, 180)
        self.assertEqual(draft.inputs_per_minute, (("iron-plate", 360.0),))
        self.assertEqual(len(draft.document["blueprint"]["entities"]), 2)
        self.assertEqual(decode(draft.exchange()), draft.document)

    def test_larger_plan_has_unique_positions(self):
        draft = self.generate(rate=1800)
        entries = draft.document["blueprint"]["entities"]
        self.assertEqual(len(entries), 20)
        self.assertEqual(len(set((e["position"]["x"], e["position"]["y"])
                                 for e in entries)), 20)

    def test_missing_machine_category_fails(self):
        bad = dict(MACHINE)
        bad.pop("crafting_categories")
        with self.assertRaises(GenerationError):
            self.generate(machine=bad)

    def test_disabled_recipe_fails(self):
        with self.assertRaises(GenerationError):
            self.generate(recipe={**RECIPE, "enabled": False})

    def test_unknown_machine_speed_fails(self):
        with self.assertRaises(GenerationError):
            self.generate(machine={**MACHINE, "crafting_speed": None})

    def test_missing_catalog_fingerprint_fails(self):
        with self.assertRaises(GenerationError):
            self.generate(fingerprint="")

    def test_unknown_target_product_fails(self):
        with self.assertRaises(GenerationError):
            self.generate(item="copper-plate")

    def test_uncertain_recipe_yield_fails(self):
        products = [{"name": "iron-gear-wheel", "amount": 1,
                     "deterministic": False}]
        with self.assertRaises(GenerationError):
            self.generate(recipe={**RECIPE, "products": products})

    def test_runtime_probability_fields_cannot_inflate_guaranteed_rate(self):
        for fields in ({"independent_probability": 0.2},
                       {"independent_probability": True},
                       {"shared_probability": {"min": 0, "max": 0.5}},
                       {"shared_probability": {"min": 0}},
                       {"shared_probability": "unknown"}):
            with self.subTest(fields=fields), self.assertRaises(GenerationError):
                self.generate(recipe={**RECIPE, "products": [
                    {**RECIPE["products"][0], **fields}]})

    def test_certain_runtime_probability_fields_keep_rate(self):
        product = {**RECIPE["products"][0], "independent_probability": 1,
                   "shared_probability": {"min": 0, "max": 1}}
        self.assertEqual(self.generate(recipe={**RECIPE, "products": [product]})
                         .expected_per_minute, 180)

    def test_unbounded_factory_refused(self):
        with self.assertRaises(GenerationError):
            self.generate(rate=10_000_000)


if __name__ == "__main__":
    unittest.main()
