"""Effective-yield model for observed Factorio 2.1.23 recipe parts.

The model must distinguish a guaranteed yield from a bounded one and from a
probabilistic one, and it must never report a falsely precise expected value
for a quantity whose game distribution is not verified.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from effective_yield import (
    combined_target_yield,
    is_catalyst_part,
    uncertainty_summary,
    yield_of_part,
    yield_of_products,
)


def part(name, amount, material_type="item", **extra):
    row = {"name": name, "amount": amount, "type": material_type}
    row.update(extra)
    return row


class GuaranteedYieldTests(unittest.TestCase):
    def test_a_plain_amount_is_guaranteed(self):
        result = yield_of_part(part("iron-plate", 1))
        self.assertEqual(result.guaranteed, 1)
        self.assertEqual(result.minimum, 1)
        self.assertEqual(result.maximum, 1)
        self.assertEqual(result.expected, 1)
        self.assertTrue(result.deterministic)
        self.assertFalse(result.is_uncertain)
        self.assertEqual(result.reasons, ())

    def test_a_zero_amount_product_is_still_guaranteed(self):
        result = yield_of_part(part("iron-plate", 0))
        self.assertEqual(result.guaranteed, 0)
        self.assertTrue(result.deterministic)

    def test_a_missing_amount_is_reported_not_guessed(self):
        result = yield_of_part({"name": "iron-plate", "type": "item"})
        self.assertEqual(result.guaranteed, 0)
        self.assertFalse(result.deterministic)
        self.assertTrue(result.reasons)

    def test_a_non_finite_amount_is_reported_not_guessed(self):
        result = yield_of_part(part("iron-plate", float("inf")))
        self.assertEqual(result.guaranteed, 0)
        self.assertFalse(result.deterministic)

    def test_a_boolean_amount_is_not_treated_as_a_number(self):
        result = yield_of_part(part("iron-plate", True))
        self.assertEqual(result.guaranteed, 0)
        self.assertFalse(result.deterministic)


class RangedYieldTests(unittest.TestCase):
    def test_a_range_keeps_its_bounds(self):
        result = yield_of_part(part("iron-ore", 1, amount_min=1, amount_max=3))
        self.assertEqual(result.minimum, 1)
        self.assertEqual(result.maximum, 3)
        self.assertIsNone(result.guaranteed)
        self.assertFalse(result.deterministic)

    def test_a_range_does_not_report_a_guessed_expected_value(self):
        """The game's distribution inside a range is not documented."""
        result = yield_of_part(part("iron-ore", 1, amount_min=1, amount_max=3))
        self.assertIsNone(result.expected)
        self.assertTrue(result.is_uncertain)
        self.assertTrue(
            any("expected yield is unknown" in r for r in result.reasons)
        )

    def test_a_range_does_not_report_a_midpoint(self):
        result = yield_of_part(part("iron-ore", 1, amount_min=1, amount_max=3))
        self.assertNotEqual(result.expected, 2)

    def test_an_inverted_range_falls_back_to_the_nominal_amount(self):
        result = yield_of_part(part("iron-ore", 2, amount_min=5, amount_max=1))
        self.assertTrue(any("inverted" in r for r in result.reasons))
        self.assertEqual(result.minimum, 2)
        self.assertEqual(result.maximum, 2)

    def test_a_range_with_only_a_minimum_uses_the_nominal_as_the_maximum(self):
        result = yield_of_part(part("iron-ore", 4, amount_min=1))
        self.assertEqual(result.minimum, 1)
        self.assertEqual(result.maximum, 4)


class ProbabilisticYieldTests(unittest.TestCase):
    def test_an_independent_probability_is_kept(self):
        result = yield_of_part(part("iron-plate", 2, independent_probability=0.25))
        self.assertEqual(result.probability, 0.25)
        self.assertIsNone(result.guaranteed)
        self.assertFalse(result.deterministic)

    def test_a_probability_of_one_stays_guaranteed(self):
        result = yield_of_part(part("iron-plate", 2, independent_probability=1))
        self.assertEqual(result.guaranteed, 2)
        self.assertIsNone(result.probability)
        self.assertTrue(result.deterministic)

    def test_a_shared_probability_makes_the_amount_uncertain(self):
        result = yield_of_part(
            part("iron-plate", 2, shared_probability={"min": 0, "max": 0.5})
        )
        self.assertIsNone(result.guaranteed)
        self.assertFalse(result.deterministic)

    def test_a_probability_of_zero_yields_nothing(self):
        result = yield_of_part(part("iron-plate", 2, independent_probability=0))
        self.assertIsNone(result.guaranteed)
        self.assertEqual(result.minimum, 0)


class ExtraFractionYieldTests(unittest.TestCase):
    def test_an_extra_fraction_adds_one_to_the_maximum(self):
        result = yield_of_part(part("iron-plate", 1, extra_count_fraction=0.5))
        self.assertEqual(result.maximum, 2)
        self.assertFalse(result.deterministic)

    def test_an_extra_fraction_of_zero_changes_nothing(self):
        result = yield_of_part(part("iron-plate", 1, extra_count_fraction=0))
        self.assertEqual(result.maximum, 1)
        self.assertTrue(result.deterministic)


class SpoilageYieldTests(unittest.TestCase):
    def test_spoilage_reduces_the_expected_amount(self):
        result = yield_of_part(part("iron-plate", 10, percent_spoiled=0.5))
        self.assertEqual(result.expected, 5)
        self.assertFalse(result.deterministic)

    def test_full_spoilage_yields_almost_nothing(self):
        result = yield_of_part(part("iron-plate", 10, percent_spoiled=0.99))
        self.assertLess(result.expected or 0, 1)

    def test_a_ranged_spoiled_product_keeps_an_unknown_expectation(self):
        result = yield_of_part(
            part("iron-ore", 1, amount_min=1, amount_max=3, percent_spoiled=0.5)
        )
        self.assertIsNone(result.expected)


class ProductivityYieldTests(unittest.TestCase):
    def test_a_productivity_restriction_is_reported(self):
        result = yield_of_part(part("iron-plate", 1, ignored_by_productivity=1))
        self.assertTrue(
            any("ignored by productivity" in r for r in result.reasons)
        )

    def test_a_productivity_restriction_does_not_change_the_amount(self):
        result = yield_of_part(part("iron-plate", 1, ignored_by_productivity=1))
        self.assertEqual(result.guaranteed, 1)
        self.assertTrue(result.deterministic)


class CombinedYieldTests(unittest.TestCase):
    def test_a_single_matching_product_is_combined(self):
        products = [part("iron-plate", 2), part("gear", 1)]
        result = combined_target_yield(products, "item", "iron-plate")
        self.assertEqual(result.guaranteed, 2)
        self.assertEqual(result.maximum, 2)

    def test_two_matching_products_are_summed(self):
        products = [part("iron-plate", 2), part("iron-plate", 3)]
        result = combined_target_yield(products, "item", "iron-plate")
        self.assertEqual(result.guaranteed, 5)
        self.assertEqual(result.maximum, 5)

    def test_a_missing_target_is_reported(self):
        result = combined_target_yield([part("gear", 1)], "item", "iron-plate")
        self.assertEqual(result.guaranteed, 0)
        self.assertFalse(result.deterministic)
        self.assertTrue(result.reasons)

    def test_a_type_mismatch_is_not_matched(self):
        products = [part("water", 100, "fluid")]
        result = combined_target_yield(products, "item", "water")
        self.assertEqual(result.guaranteed, 0)

    def test_a_combined_uncertain_product_has_no_expected_value(self):
        products = [
            part("iron-plate", 2),
            part("iron-plate", 1, amount_min=1, amount_max=3),
        ]
        result = combined_target_yield(products, "item", "iron-plate")
        self.assertIsNone(result.expected)
        self.assertIsNone(result.guaranteed)


class HelperTests(unittest.TestCase):
    def test_yield_of_products_returns_one_entry_per_product(self):
        yields = yield_of_products([part("a", 1), part("b", 2)])
        self.assertEqual(len(yields), 2)
        self.assertEqual(yields[1].guaranteed, 2)

    def test_uncertainty_summary_deduplicates_the_reasons(self):
        yields = yield_of_products([
            part("a", 1, independent_probability=0.5),
            part("b", 1, independent_probability=0.5),
        ])
        reasons = uncertainty_summary(yields)
        self.assertEqual(len(reasons), len(set(reasons)))

    def test_a_catalyst_is_not_guessed(self):
        """The catalog cannot express a catalyst, so none is invented."""
        self.assertFalse(is_catalyst_part(part("iron-ore", 1)))
        self.assertTrue(is_catalyst_part(part("iron-ore", 1, catalyst=True)))

    def test_the_yield_serialises_to_a_plain_dict(self):
        data = yield_of_part(part("iron-plate", 1)).as_dict()
        self.assertEqual(data["amount"], 1)
        self.assertTrue(data["deterministic"])
        self.assertFalse(data["is_uncertain"])


class YieldSerializationTests(unittest.TestCase):
    def test_every_yield_key_is_always_present(self):
        """A consumer must be able to tell "not reported" from "missing"."""
        data = yield_of_part(part("iron-plate", 1)).as_dict()
        for key in ("amount", "guaranteed", "minimum", "maximum", "expected",
                    "probability", "deterministic", "is_uncertain", "reasons"):
            self.assertIn(key, data)

    def test_a_reported_probability_is_kept_in_the_serialisation(self):
        data = yield_of_part(
            part("iron-plate", 1, independent_probability=0.25)
        ).as_dict()
        self.assertEqual(data["probability"], 0.25)


class CombinedProbabilityTests(unittest.TestCase):
    def test_a_single_probabilistic_product_keeps_its_probability(self):
        products = [part("gem", 1, independent_probability=0.25)]
        result = combined_target_yield(products, "item", "gem")
        self.assertEqual(result.probability, 0.25)

    def test_two_probabilistic_products_do_not_assert_a_combined_probability(self):
        """The chance that any of two products appears is not the product."""
        products = [
            part("gem", 1, independent_probability=0.25),
            part("gem", 1, independent_probability=0.5),
        ]
        result = combined_target_yield(products, "item", "gem")
        self.assertIsNone(result.probability)
        self.assertFalse(result.deterministic)


if __name__ == "__main__":
    unittest.main()
