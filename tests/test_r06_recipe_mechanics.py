"""R06: Factorio 2.1.23 recipe mechanic support in the backend adapter.

The backend recipe adapter historically rejected any product or ingredient
carrying a field it did not recognise. Real Factorio 2.1.23 recipes carry
several documented fields, so every such recipe was dropped from the catalog
entirely (the live Pyanodons run kept 7,807 of 10,146 recipes).

Each test extracts the *real* ``normalized_parts`` Lua function from
backend-safety/Tools/RecipeResearchAdapter.cs and executes it against a
representative 2.1.23 recipe shape, so the shipped logic is proved by
behaviour rather than by a string match.

The authoritative field lists come from the verified offline 2.1.23
prototype API (.local/factorio-api-offline/2.1.23/files/prototype-api.json).
"""

import unittest
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"
API = ROOT / ".local" / "factorio-api-offline" / "2.1.23" / "files" / "prototype-api.json"


def lua_value(value: Any) -> str:
    """Render a Python value as a Lua literal."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value != value:
            return "0/0"
        if value == float("inf"):
            return "math.huge"
        if value == float("-inf"):
            return "-math.huge"
        return repr(value)
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, dict):
        parts = [f"[{lua_value(k)}]={lua_value(v)}" for k, v in value.items()]
        return "{" + ",".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(lua_value(v) for v in value) + "}"
    if isinstance(value, set):
        return "{" + ",".join(lua_value(v) for v in sorted(value)) + "}"
    raise TypeError(f"unsupported Lua literal: {value!r}")


class RecipeMechanicsTests(unittest.TestCase):
    """The real adapter Lua must accept the real 2.1.23 recipe fields."""

    @classmethod
    def setUpClass(cls):
        cls.source = ADAPTER.read_text(encoding="utf-8")
        start = cls.source.index("local function normalized_parts(")
        end = cls.source.index("\n                        for i=first,last do", start)
        cls.lua_function = cls.source[start:end]

    def setUp(self):
        try:
            import lupa  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("lupa is not installed; the Lua contract cannot run")

    def normalize(
        self,
        products: list[dict[str, Any]],
        ingredients: list[dict[str, Any]] | None = None,
    ) -> tuple[Any, Any]:
        """Run the real adapter normalizer and return (products, ingredients).

        A ``None`` result means the adapter rejected the recipe shape. Lua
        drops nil table members, so a rejected list is reported with an
        explicit ``rejected`` flag instead of a missing key.
        """
        import lupa

        program = (
            self.lua_function
            + "\n"
            + f"local products = {lua_value(list(products))}\n"
            + f"local ingredients = {lua_value(list(ingredients or []))}\n"
            + "local p = normalized_parts(products, 8, true)\n"
            + "local i = normalized_parts(ingredients, 16, false)\n"
            + "return {p=p or false,i=i or false,"
            + "rejected_p=(p==nil),rejected_i=(i==nil)}\n"
        )
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        result = lua.execute(program)
        result = cast(
            dict[str, Any],
            result if isinstance(result, dict) else dict(result),  # type: ignore[arg-type]
        )
        products_out = None if bool(result["rejected_p"]) else result["p"]
        ingredients_out = None if bool(result["rejected_i"]) else result["i"]
        return products_out, ingredients_out

    # -- the contract ------------------------------------------------------

    def test_a_fluid_product_with_a_temperature_is_kept(self):
        """Factorio 2.1.23 FluidProductPrototype declares ``temperature``.

        A recipe such as ``steam-turbine`` or every Space Age boiler
        produces a fluid at a specific temperature. The adapter rejected the
        whole recipe because ``temperature`` was not an accepted field, so
        those recipes were missing from the catalog.
        """
        products, _ = self.normalize([
            {"name": "steam", "type": "fluid", "amount": 100, "temperature": 15},
        ])
        self.assertIsNotNone(products, "a fluid product with a temperature was dropped")
        self.assertEqual(products[1]["temperature"], 15)

    def test_a_fluid_ingredient_with_a_temperature_window_is_kept(self):
        """Factorio 2.1.23 FluidIngredientPrototype declares
        ``minimum_temperature`` and ``maximum_temperature``.

        A recipe that only accepts a fluid inside a temperature window is a
        real 2.1.23 mechanic and must not be dropped from the catalog.
        """
        _products, ingredients = self.normalize(
            [{"name": "steam", "type": "fluid", "amount": 100}],
            [{
                "name": "water",
                "type": "fluid",
                "amount": 50,
                "minimum_temperature": 15,
                "maximum_temperature": 100,
            }],
        )
        self.assertIsNotNone(
            ingredients,
            "a fluid ingredient with a temperature window was dropped",
        )
        self.assertEqual(ingredients[1]["minimum_temperature"], 15)
        self.assertEqual(ingredients[1]["maximum_temperature"], 100)

    def test_an_unknown_field_is_still_rejected(self):
        """Accepting real 2.1.23 fields must not weaken the fail-closed rule.

        A field that is not part of the verified 2.1.23 product/ingredient
        prototypes must still cause the recipe to be rejected, so unknown or
        modded semantics are never silently presented as modelled.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "not_a_real_factorio_field": True},
        ])
        self.assertIsNone(products, "an unknown field was accepted")

    def test_a_non_fluid_must_not_carry_a_temperature(self):
        """``temperature`` is a fluid-only field.

        An item product that claims a temperature is not a valid 2.1.23
        shape, so it must be rejected rather than modelled as a fluid rule.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1, "temperature": 15},
        ])
        self.assertIsNone(products, "an item product with a temperature was accepted")

    def test_a_non_finite_temperature_is_rejected(self):
        """A temperature must be a finite number."""
        products, _ = self.normalize([
            {"name": "steam", "type": "fluid", "amount": 100,
             "temperature": float("inf")},
        ])
        self.assertIsNone(products, "a non-finite temperature was accepted")

    def test_the_temperature_fields_match_the_verified_2123_api(self):
        """The accepted temperature fields must exist in the 2.1.23 API."""
        import json

        data = json.loads(API.read_text(encoding="utf-8"))
        types = {t["name"]: t for t in data["types"]}

        def field_names(type_name: str) -> set[str]:
            names: set[str] = set()
            seen: set[str] = set()
            current: str | None = type_name
            while current and current in types and current not in seen:
                seen.add(current)
                proto = types[current]
                for prop in proto.get("properties", []):
                    names.add(prop.get("name"))
                current = proto.get("parent")
            return names

        self.assertIn("temperature", field_names("FluidProductPrototype"))
        self.assertIn("temperature", field_names("FluidIngredientPrototype"))
        self.assertIn("minimum_temperature", field_names("FluidIngredientPrototype"))
        self.assertIn("maximum_temperature", field_names("FluidIngredientPrototype"))
        self.assertNotIn("temperature", field_names("ItemProductPrototype"))

    def test_the_adapter_still_keeps_a_plain_recipe_simple(self):
        """A plain single-item product with no temperature stays simple."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1},
        ])
        self.assertIsNotNone(products)
        self.assertNotIn("deterministic", products[1])

    # -- quality mechanics -------------------------------------------------

    def test_a_product_with_quality_bounds_is_kept(self):
        """Factorio 2.1.23 ItemProductPrototype declares ``quality_min`` and
        ``quality_max`` as QualityID strings.

        A Space Age recipe whose result quality is bounded is a real 2.1.23
        mechanic. It must not be dropped from the catalog.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_min": "normal", "quality_max": "legendary"},
        ])
        self.assertIsNotNone(products, "a product with quality bounds was dropped")
        self.assertEqual(products[1]["quality_min"], "normal")
        self.assertEqual(products[1]["quality_max"], "legendary")

    def test_an_ingredient_with_quality_bounds_is_kept(self):
        """Factorio 2.1.23 ItemIngredientPrototype declares the same
        ``quality_min`` and ``quality_max`` QualityID fields."""
        _products, ingredients = self.normalize(
            [{"name": "iron-plate", "type": "item", "amount": 1}],
            [{"name": "iron-ore", "type": "item", "amount": 1,
              "quality_min": "normal", "quality_max": "rare"}],
        )
        self.assertIsNotNone(
            ingredients, "an ingredient with quality bounds was dropped"
        )
        self.assertEqual(ingredients[1]["quality_max"], "rare")

    def test_a_modded_quality_name_is_preserved_verbatim(self):
        """QualityID is any QualityPrototype name.

        A mod may add its own quality tier, so the observed name must be
        preserved rather than validated against the five vanilla tiers.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_max": "py-supreme"},
        ])
        self.assertIsNotNone(products)
        self.assertEqual(products[1]["quality_max"], "py-supreme")

    def test_a_quality_change_is_kept(self):
        """Factorio 2.1.23 declares ``quality_change`` as an int8.

        It is the number of quality levels the product is adjusted by, and
        it applies to both products and ingredients.
        """
        products, ingredients = self.normalize(
            [{"name": "iron-plate", "type": "item", "amount": 1,
              "quality_change": 1}],
            [{"name": "iron-ore", "type": "item", "amount": 1,
              "quality_change": -1}],
        )
        self.assertIsNotNone(products, "a product with a quality change was dropped")
        self.assertEqual(products[1]["quality_change"], 1)
        self.assertIsNotNone(
            ingredients, "an ingredient with a quality change was dropped"
        )
        self.assertEqual(ingredients[1]["quality_change"], -1)

    def test_a_non_numeric_quality_name_is_rejected(self):
        """A quality bound must be a name, not a number."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_min": 3},
        ])
        self.assertIsNone(products, "a numeric quality bound was accepted")

    def test_a_non_integer_quality_change_is_rejected(self):
        """``quality_change`` is an int8, so a fractional value is invalid."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_change": 0.5},
        ])
        self.assertIsNone(products, "a fractional quality change was accepted")

    def test_a_fluid_must_not_carry_a_quality_bound(self):
        """Quality bounds are declared by the item prototypes only."""
        products, _ = self.normalize([
            {"name": "steam", "type": "fluid", "amount": 100,
             "quality_min": "normal"},
        ])
        self.assertIsNone(products, "a fluid product with a quality bound was accepted")

    def test_the_quality_fields_match_the_verified_2123_api(self):
        """The accepted quality fields must exist in the 2.1.23 API."""
        import json

        data = json.loads(API.read_text(encoding="utf-8"))
        types = {t["name"]: t for t in data["types"]}

        def field_names(type_name: str) -> set[str]:
            names: set[str] = set()
            seen: set[str] = set()
            current: str | None = type_name
            while current and current in types and current not in seen:
                seen.add(current)
                for prop in types[current].get("properties", []):
                    names.add(prop.get("name"))
                current = types[current].get("parent")
            return names

        for field in ("quality_min", "quality_max", "quality_change"):
            self.assertIn(field, field_names("ItemProductPrototype"))
            self.assertIn(field, field_names("ItemIngredientPrototype"))
        self.assertNotIn("quality_min", field_names("FluidProductPrototype"))
        self.assertNotIn("quality_min", field_names("FluidIngredientPrototype"))


# -- quantity range and probabilistic extra output ---------------------

    def test_a_product_with_a_quantity_range_is_kept(self):
        """Factorio 2.1.23 ItemProductPrototype declares ``amount_min`` and
        ``amount_max`` as uint16.

        A product with a quantity range is not a fixed amount, so the
        planner must be told the range instead of guessing a single number.
        """
        products, _ = self.normalize([
            {"name": "iron-ore", "type": "item", "amount": 1,
             "amount_min": 1, "amount_max": 3},
        ])
        self.assertIsNotNone(products, "a product with a quantity range was dropped")
        self.assertEqual(products[1]["amount_min"], 1)
        self.assertEqual(products[1]["amount_max"], 3)

    def test_a_range_product_is_not_deterministic(self):
        """A quantity range means the yield is not a fixed amount.

        The row must be marked as not deterministic, so the planner never
        treats the nominal amount as the guaranteed yield.
        """
        products, _ = self.normalize([
            {"name": "iron-ore", "type": "item", "amount": 1,
             "amount_min": 1, "amount_max": 3},
        ])
        self.assertIsNotNone(products)
        self.assertEqual(products[1]["deterministic"], False)

    def test_an_extra_count_fraction_is_kept_and_is_not_deterministic(self):
        """Factorio 2.1.23 declares ``extra_count_fraction`` as a float.

        It is the probability that a craft yields one additional product,
        so the product is not deterministic.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "extra_count_fraction": 0.5},
        ])
        self.assertIsNotNone(products, "a product with an extra count fraction was dropped")
        self.assertEqual(products[1]["extra_count_fraction"], 0.5)
        self.assertEqual(products[1]["deterministic"], False)

    def test_an_extra_count_fraction_of_one_stays_deterministic(self):
        """A fraction of 1 means the extra product is certain."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "extra_count_fraction": 1},
        ])
        self.assertIsNotNone(products)
        self.assertNotIn("deterministic", products[1])

    def test_an_out_of_range_extra_count_fraction_is_rejected(self):
        """The fraction is a probability, so it must be within 0..1."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "extra_count_fraction": 1.5},
        ])
        self.assertIsNone(products, "an out-of-range extra count fraction was accepted")

    def test_an_inverted_quantity_range_is_rejected(self):
        """``amount_max`` below ``amount_min`` is not a valid 2.1.23 shape."""
        products, _ = self.normalize([
            {"name": "iron-ore", "type": "item", "amount": 1,
             "amount_min": 5, "amount_max": 2},
        ])
        self.assertIsNone(products, "an inverted quantity range was accepted")

    def test_a_fractional_quantity_range_is_rejected(self):
        """``amount_min`` and ``amount_max`` are uint16, so they are whole."""
        products, _ = self.normalize([
            {"name": "iron-ore", "type": "item", "amount": 1,
             "amount_min": 1.5, "amount_max": 3},
        ])
        self.assertIsNone(products, "a fractional quantity range was accepted")

    def test_a_quantity_range_on_an_ingredient_is_rejected(self):
        """The range fields are declared by the product prototypes only."""
        _products, ingredients = self.normalize(
            [{"name": "iron-plate", "type": "item", "amount": 1}],
            [{"name": "iron-ore", "type": "item", "amount": 1, "amount_min": 1}],
        )
        self.assertIsNone(ingredients, "an ingredient with a quantity range was accepted")

    def test_the_quantity_fields_match_the_verified_2123_api(self):
        """The accepted quantity fields must exist in the 2.1.23 API."""
        import json

        data = json.loads(API.read_text(encoding="utf-8"))
        types = {t["name"]: t for t in data["types"]}

        def field_names(type_name: str) -> set[str]:
            names: set[str] = set()
            seen: set[str] = set()
            current: str | None = type_name
            while current and current in types and current not in seen:
                seen.add(current)
                for prop in types[current].get("properties", []):
                    names.add(prop.get("name"))
                current = types[current].get("parent")
            return names

        for field in ("amount_min", "amount_max"):
            self.assertIn(field, field_names("ItemProductPrototype"))
            self.assertIn(field, field_names("FluidProductPrototype"))
        self.assertIn("extra_count_fraction", field_names("ItemProductPrototype"))
        self.assertNotIn("amount_min", field_names("ItemIngredientPrototype"))
        self.assertNotIn("extra_count_fraction", field_names("ItemIngredientPrototype"))


# -- productivity and freshness mechanics ------------------------------

    def test_a_product_ignored_by_productivity_is_kept(self):
        """Factorio 2.1.23 declares ``ignored_by_productivity`` as a uint16.

        It is the amount deducted from a productivity-induced bonus craft, so
        a productivity-restricted product is a real mechanic.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_productivity": 1},
        ])
        self.assertIsNotNone(products, "a productivity-restricted product was dropped")
        self.assertEqual(products[1]["ignored_by_productivity"], 1)

    def test_the_freshness_flags_are_kept(self):
        """Factorio 2.1.23 declares ``always_fresh`` and
        ``reset_freshness_on_craft`` as booleans."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "always_fresh": True, "reset_freshness_on_craft": True},
        ])
        self.assertIsNotNone(products, "a product with freshness flags was dropped")
        self.assertEqual(products[1]["always_fresh"], True)
        self.assertEqual(products[1]["reset_freshness_on_craft"], True)

    def test_a_percent_spoiled_product_is_kept(self):
        """Factorio 2.1.23 declares ``percent_spoiled`` as a float in 0..1.

        A spoiled output is a real mechanic, and the observed fraction must
        be preserved so the planner can report the effective yield.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "percent_spoiled": 0.5},
        ])
        self.assertIsNotNone(products, "a spoiled product was dropped")
        self.assertEqual(products[1]["percent_spoiled"], 0.5)

    def test_a_percent_spoiled_of_one_is_rejected(self):
        """``percent_spoiled`` must be >= 0 and < 1."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "percent_spoiled": 1},
        ])
        self.assertIsNone(products, "a percent_spoiled of 1 was accepted")

    def test_a_negative_percent_spoiled_is_rejected(self):
        """``percent_spoiled`` must be >= 0."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "percent_spoiled": -0.1},
        ])
        self.assertIsNone(products, "a negative percent_spoiled was accepted")

    def test_a_negative_ignored_by_productivity_is_rejected(self):
        """``ignored_by_productivity`` is a uint16, so it cannot be negative."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_productivity": -1},
        ])
        self.assertIsNone(products, "a negative ignored_by_productivity was accepted")

    def test_the_freshness_fields_match_the_verified_2123_api(self):
        """The accepted freshness and productivity fields must exist in 2.1.23."""
        import json

        data = json.loads(API.read_text(encoding="utf-8"))
        types = {t["name"]: t for t in data["types"]}

        def field_names(type_name: str) -> set[str]:
            names: set[str] = set()
            seen: set[str] = set()
            current: str | None = type_name
            while current and current in types and current not in seen:
                seen.add(current)
                for prop in types[current].get("properties", []):
                    names.add(prop.get("name"))
                current = types[current].get("parent")
            return names

        for field in ("ignored_by_productivity", "always_fresh",
                      "reset_freshness_on_craft", "percent_spoiled"):
            self.assertIn(field, field_names("ItemProductPrototype"))
        self.assertIn("ignored_by_productivity", field_names("FluidProductPrototype"))
        self.assertNotIn("percent_spoiled", field_names("FluidProductPrototype"))
        self.assertNotIn("always_fresh", field_names("ItemIngredientPrototype"))


# -- fluidbox index and tooltip display mechanics ----------------------

    def test_a_fluid_with_optional_fluidbox_indexes_is_kept(self):
        """Factorio 2.1.23 FluidProductPrototype declares
        ``optional_fluidbox_indexes`` as an array of uint32.

        A fluid that may occupy more than one fluid box is a real mechanic
        and must not be dropped from the catalog.
        """
        products, _ = self.normalize([
            {"name": "steam", "type": "fluid", "amount": 100,
             "optional_fluidbox_indexes": {1, 2}},
        ])
        self.assertIsNotNone(products, "a fluid with optional fluidbox indexes was dropped")
        self.assertEqual(sorted(products[1]["optional_fluidbox_indexes"]), [1, 2])

    def test_a_tooltip_display_flag_is_kept(self):
        """Factorio 2.1.23 ProductPrototypeBase declares
        ``show_details_in_recipe_tooltip`` as a boolean.

        It is a display-only flag, but it is a real 2.1.23 field, so the
        recipe must still be kept.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "show_details_in_recipe_tooltip": False},
        ])
        self.assertIsNotNone(products, "a product with a tooltip flag was dropped")
        self.assertEqual(products[1]["show_details_in_recipe_tooltip"], False)

    def test_a_fluidbox_index_on_an_item_is_rejected(self):
        """``optional_fluidbox_indexes`` is declared by the fluid prototypes."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "optional_fluidbox_indexes": {1}},
        ])
        self.assertIsNone(products, "an item with optional fluidbox indexes was accepted")

    def test_a_negative_fluidbox_index_is_rejected(self):
        """The indexes are uint32, so they cannot be negative."""
        products, _ = self.normalize([
            {"name": "steam", "type": "fluid", "amount": 100,
             "optional_fluidbox_indexes": {-1}},
        ])
        self.assertIsNone(products, "a negative fluidbox index was accepted")

    def test_a_non_boolean_tooltip_flag_is_rejected(self):
        """The tooltip flag is a boolean."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "show_details_in_recipe_tooltip": 1},
        ])
        self.assertIsNone(products, "a non-boolean tooltip flag was accepted")

    def test_the_display_fields_match_the_verified_2123_api(self):
        """The accepted display fields must exist in the 2.1.23 API."""
        import json

        data = json.loads(API.read_text(encoding="utf-8"))
        types = {t["name"]: t for t in data["types"]}

        def field_names(type_name: str) -> set[str]:
            names: set[str] = set()
            seen: set[str] = set()
            current: str | None = type_name
            while current and current in types and current not in seen:
                seen.add(current)
                for prop in types[current].get("properties", []):
                    names.add(prop.get("name"))
                current = types[current].get("parent")
            return names

        for field in ("optional_fluidbox_indexes",):
            self.assertIn(field, field_names("FluidProductPrototype"))
            self.assertIn(field, field_names("FluidIngredientPrototype"))
        # show_details_in_recipe_tooltip is declared by ProductPrototypeBase,
        # so it belongs to the product prototypes only.
        self.assertIn(
            "show_details_in_recipe_tooltip", field_names("ItemProductPrototype")
        )
        self.assertIn(
            "show_details_in_recipe_tooltip", field_names("FluidProductPrototype")
        )
        self.assertNotIn(
            "show_details_in_recipe_tooltip", field_names("FluidIngredientPrototype")
        )
        self.assertNotIn(
            "optional_fluidbox_indexes", field_names("ItemProductPrototype")
        )


# -- ignored_by_stats numeric amount ----------------------------------

    def test_an_ignored_by_stats_amount_is_kept(self):
        """Factorio 2.1.23 declares ``ignored_by_stats`` as a uint16 on the
        item prototypes and a FluidAmount on the fluid prototypes.

        It is the amount excluded from the production or consumption
        statistics, so it is a number and must be preserved exactly.
        """
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": 5},
        ])
        self.assertIsNotNone(products, "a product with an ignored_by_stats amount was dropped")
        self.assertEqual(products[1]["ignored_by_stats"], 5)

    def test_an_ignored_by_stats_amount_is_kept_on_an_ingredient(self):
        """The field is declared on the ingredient prototypes as well."""
        _products, ingredients = self.normalize(
            [{"name": "iron-plate", "type": "item", "amount": 1}],
            [{"name": "iron-ore", "type": "item", "amount": 1,
              "ignored_by_stats": 3}],
        )
        self.assertIsNotNone(
            ingredients, "an ingredient with an ignored_by_stats amount was dropped"
        )
        self.assertEqual(ingredients[1]["ignored_by_stats"], 3)

    def test_a_boolean_ignored_by_stats_is_rejected(self):
        """The 2.1.23 field is numeric, so a boolean is not a valid shape."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": True},
        ])
        self.assertIsNone(products, "a boolean ignored_by_stats was accepted")

    def test_a_negative_ignored_by_stats_is_rejected(self):
        """An item amount is a uint16, so it cannot be negative."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": -1},
        ])
        self.assertIsNone(products, "a negative ignored_by_stats was accepted")

    def test_a_fractional_item_ignored_by_stats_is_rejected(self):
        """An item amount is a whole number."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": 1.5},
        ])
        self.assertIsNone(products, "a fractional item ignored_by_stats was accepted")

    def test_an_out_of_range_item_ignored_by_stats_is_rejected(self):
        """A uint16 holds at most 65535."""
        products, _ = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": 65536},
        ])
        self.assertIsNone(products, "an out-of-range item ignored_by_stats was accepted")

    def test_a_fractional_fluid_ignored_by_stats_is_kept(self):
        """A fluid amount is a FluidAmount, so it may be fractional."""
        products, _ = self.normalize([
            {"name": "steam", "type": "fluid", "amount": 100,
             "ignored_by_stats": 12.5},
        ])
        self.assertIsNotNone(products, "a fractional fluid ignored_by_stats was dropped")
        self.assertEqual(products[1]["ignored_by_stats"], 12.5)

    def test_a_negative_fluid_ignored_by_stats_is_rejected(self):
        """A fluid amount cannot be negative either."""
        products, _ = self.normalize([
            {"name": "steam", "type": "fluid", "amount": 100,
             "ignored_by_stats": -0.5},
        ])
        self.assertIsNone(products, "a negative fluid ignored_by_stats was accepted")

    def test_the_ignored_by_stats_type_matches_the_verified_2123_api(self):
        """The accepted type must match the verified 2.1.23 API."""
        import json

        data = json.loads(API.read_text(encoding="utf-8"))
        types = {t["name"]: t for t in data["types"]}

        def property_of(type_name: str, field: str) -> dict[str, Any] | None:
            seen: set[str] = set()
            current: str | None = type_name
            while current and current in types and current not in seen:
                seen.add(current)
                for prop in types[current].get("properties", []):
                    if prop.get("name") == field:
                        return prop
                current = types[current].get("parent")
            return None

        for type_name in ("ItemProductPrototype", "ItemIngredientPrototype"):
            prop = property_of(type_name, "ignored_by_stats")
            self.assertIsNotNone(prop, f"{type_name} has no ignored_by_stats")
            assert prop is not None
            self.assertEqual(prop["type"], "uint16")
        for type_name in ("FluidProductPrototype", "FluidIngredientPrototype"):
            prop = property_of(type_name, "ignored_by_stats")
            self.assertIsNotNone(prop, f"{type_name} has no ignored_by_stats")
            assert prop is not None
            declared = prop["type"]
            if isinstance(declared, dict):
                declared = declared.get("complex_type")
            self.assertEqual(declared, "FluidAmount")


class CapabilityValidatorTemperatureTests(unittest.TestCase):
    """The Python capability validator must accept the observed temperature.

    ``validate_capabilities`` fails closed on any part field it does not
    recognise. The backend now reports the observed 2.1.23 fluid temperature
    fields, so the validator must accept exactly those keys and still reject
    everything else.
    """

    @staticmethod
    def _caps(recipe):
        return {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player",
            "research": ["automation"], "enabled_content": ["base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [recipe],
        }

    @staticmethod
    def _recipe(products, ingredients=()):
        return {
            "name": "steam-turbine", "enabled": True, "hidden": False,
            "simple": False, "category": "crafting", "crafting_time": 2.0,
            "ingredients": list(ingredients),
            "products": list(products),
        }

    def test_a_fluid_product_temperature_is_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "steam", "type": "fluid", "amount": 100, "temperature": 15},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["temperature"], 15)

    def test_a_fluid_ingredient_temperature_window_is_accepted(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe(
            [{"name": "steam", "type": "fluid", "amount": 100}],
            [{
                "name": "water", "type": "fluid", "amount": 50,
                "minimum_temperature": 15, "maximum_temperature": 100,
            }],
        ))
        parsed = validate_capabilities(caps, "nauvis", 120)
        ingredient = parsed["recipes"][0]["ingredients"][0]
        self.assertEqual(ingredient["minimum_temperature"], 15)
        self.assertEqual(ingredient["maximum_temperature"], 100)

    def test_an_unknown_part_key_is_still_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "steam", "type": "fluid", "amount": 100,
             "not_a_real_factorio_field": 1},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_non_finite_temperature_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "steam", "type": "fluid", "amount": 100,
             "temperature": float("inf")},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_temperature_on_an_item_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "temperature": 15},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)


class CapabilityValidatorQualityTests(unittest.TestCase):
    """The Python capability validator must accept the observed quality keys.

    The backend now reports the observed 2.1.23 quality bounds and quality
    change, so the validator must accept exactly those keys on an item and
    still reject everything else.
    """

    @staticmethod
    def _caps(recipe):
        return {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player",
            "research": ["automation"], "enabled_content": ["base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [recipe],
        }

    @staticmethod
    def _recipe(products, ingredients=()):
        return {
            "name": "quality-recipe", "enabled": True, "hidden": False,
            "simple": False, "category": "crafting", "crafting_time": 0.5,
            "ingredients": list(ingredients),
            "products": list(products),
        }

    def test_quality_bounds_are_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_min": "normal", "quality_max": "legendary"},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["quality_min"], "normal")
        self.assertEqual(product["quality_max"], "legendary")

    def test_a_modded_quality_name_is_accepted(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_max": "py-supreme"},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        self.assertEqual(
            parsed["recipes"][0]["products"][0]["quality_max"], "py-supreme"
        )

    def test_a_quality_change_is_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_change": -1},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        self.assertEqual(
            parsed["recipes"][0]["products"][0]["quality_change"], -1
        )

    def test_a_quality_bound_on_a_fluid_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "steam", "type": "fluid", "amount": 100,
             "quality_min": "normal"},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_fractional_quality_change_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "quality_change": 0.5},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)


class CapabilityValidatorQuantityTests(unittest.TestCase):
    """The Python capability validator must accept the observed quantity keys.

    A ranged product and a probabilistic extra output both change what the
    nominal amount means, so the validator must accept the observed bounds
    and keep the product marked as not deterministic.
    """

    @staticmethod
    def _caps(recipe):
        return {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player",
            "research": ["automation"], "enabled_content": ["base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [recipe],
        }

    @staticmethod
    def _recipe(products):
        return {
            "name": "range-recipe", "enabled": True, "hidden": False,
            "simple": False, "category": "crafting", "crafting_time": 1.0,
            "ingredients": [], "products": list(products),
        }

    def test_a_quantity_range_is_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-ore", "type": "item", "amount": 1,
             "amount_min": 1, "amount_max": 3, "deterministic": False},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["amount_min"], 1)
        self.assertEqual(product["amount_max"], 3)
        self.assertFalse(product["deterministic"])

    def test_an_extra_count_fraction_is_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "extra_count_fraction": 0.5, "deterministic": False},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["extra_count_fraction"], 0.5)

    def test_an_out_of_range_extra_count_fraction_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "extra_count_fraction": 1.5, "deterministic": False},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_an_inverted_quantity_range_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-ore", "type": "item", "amount": 1,
             "amount_min": 5, "amount_max": 2, "deterministic": False},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_quantity_range_on_an_ingredient_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps({
            "name": "range-recipe", "enabled": True, "hidden": False,
            "simple": False, "category": "crafting", "crafting_time": 1.0,
            "ingredients": [{"name": "iron-ore", "type": "item", "amount": 1,
                             "amount_min": 1}],
            "products": [{"name": "iron-plate", "type": "item", "amount": 1}],
        })
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)


class CapabilityValidatorProductivityTests(unittest.TestCase):
    """The Python capability validator must accept the productivity fields.

    A productivity restriction and a spoilage fraction both change the
    effective yield, so the observed values must be preserved rather than
    dropped or guessed.
    """

    @staticmethod
    def _caps(recipe):
        return {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player",
            "research": ["automation"], "enabled_content": ["base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [recipe],
        }

    @staticmethod
    def _recipe(products, ingredients=()):
        return {
            "name": "productivity-recipe", "enabled": True, "hidden": False,
            "simple": False, "category": "crafting", "crafting_time": 1.0,
            "ingredients": list(ingredients), "products": list(products),
        }

    def test_the_productivity_fields_are_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_productivity": 2, "always_fresh": True,
             "reset_freshness_on_craft": True, "percent_spoiled": 0.25},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["ignored_by_productivity"], 2)
        self.assertTrue(product["always_fresh"])
        self.assertTrue(product["reset_freshness_on_craft"])
        self.assertEqual(product["percent_spoiled"], 0.25)

    def test_a_percent_spoiled_of_one_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "percent_spoiled": 1},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_negative_ignored_by_productivity_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_productivity": -1},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_freshness_flag_on_an_ingredient_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe(
            [{"name": "iron-plate", "type": "item", "amount": 1}],
            [{"name": "iron-ore", "type": "item", "amount": 1,
              "always_fresh": True}],
        ))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)


class CapabilityValidatorDisplayTests(unittest.TestCase):
    """The Python capability validator must accept the display fields."""

    @staticmethod
    def _caps(recipe):
        return {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player",
            "research": ["automation"], "enabled_content": ["base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [recipe],
        }

    @staticmethod
    def _recipe(products, ingredients=()):
        return {
            "name": "display-recipe", "enabled": True, "hidden": False,
            "simple": False, "category": "crafting", "crafting_time": 1.0,
            "ingredients": list(ingredients), "products": list(products),
        }

    def test_optional_fluidbox_indexes_are_accepted_and_sorted(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "steam", "type": "fluid", "amount": 100,
             "optional_fluidbox_indexes": [2, 1]},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["optional_fluidbox_indexes"], [1, 2])

    def test_a_tooltip_flag_is_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "show_details_in_recipe_tooltip": False},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertIs(product["show_details_in_recipe_tooltip"], False)

    def test_optional_fluidbox_indexes_on_an_item_are_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "optional_fluidbox_indexes": [1]},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_tooltip_flag_on_an_ingredient_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe(
            [{"name": "iron-plate", "type": "item", "amount": 1}],
            [{"name": "iron-ore", "type": "item", "amount": 1,
              "show_details_in_recipe_tooltip": True}],
        ))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_duplicate_fluidbox_index_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "steam", "type": "fluid", "amount": 100,
             "optional_fluidbox_indexes": [1, 1]},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)


class CapabilityValidatorIgnoredByStatsTests(unittest.TestCase):
    """The Python capability validator must accept the numeric amount.

    Factorio 2.1.23 declares ``ignored_by_stats`` as a uint16 on the item
    prototypes and a FluidAmount on the fluid ones, on both products and
    ingredients. The exact value must be preserved, never coerced.
    """

    @staticmethod
    def _caps(recipe):
        return {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player",
            "research": ["automation"], "enabled_content": ["base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [recipe],
        }

    @staticmethod
    def _recipe(products, ingredients=()):
        return {
            "name": "stats-recipe", "enabled": True, "hidden": False,
            "simple": False, "category": "crafting", "crafting_time": 1.0,
            "ingredients": list(ingredients), "products": list(products),
        }

    def test_an_item_amount_is_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": 5},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["ignored_by_stats"], 5)

    def test_an_ingredient_amount_is_accepted_and_preserved(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe(
            [{"name": "iron-plate", "type": "item", "amount": 1}],
            [{"name": "iron-ore", "type": "item", "amount": 1,
              "ignored_by_stats": 3}],
        ))
        parsed = validate_capabilities(caps, "nauvis", 120)
        ingredient = parsed["recipes"][0]["ingredients"][0]
        self.assertEqual(ingredient["ignored_by_stats"], 3)

    def test_a_boolean_amount_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": True},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_negative_amount_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": -1},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_fractional_item_amount_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": 1.5},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_an_out_of_range_item_amount_is_rejected(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "ignored_by_stats": 65536},
        ]))
        with self.assertRaises(ValueError):
            validate_capabilities(caps, "nauvis", 120)

    def test_a_fractional_fluid_amount_is_accepted(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        caps = self._caps(self._recipe([
            {"name": "steam", "type": "fluid", "amount": 100,
             "ignored_by_stats": 12.5},
        ]))
        parsed = validate_capabilities(caps, "nauvis", 120)
        product = parsed["recipes"][0]["products"][0]
        self.assertEqual(product["ignored_by_stats"], 12.5)


class CatalogOnlyCostTests(unittest.TestCase):
    def test_catalog_only_excludes_production_and_power_scans(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn("bool catalogOnly = false", source)
        self.assertIn("AUTOENGINEER_CATALOG_ONLY", source)
        self.assertIn("if not AUTOENGINEER_CATALOG_ONLY then", source)
        self.assertIn("end -- Catalog-only reads never scan", source)


class ProbabilityFieldPreservationTests(unittest.TestCase):
    """The observed probability must reach the planner, not just a flag.

    Factorio 2.1.23 ``ProductPrototypeBase`` declares
    ``independent_probability`` (a double) and ``shared_probability`` (a
    ``{min,max}`` definition). The adapter already marked a product with a
    probability below one as ``deterministic = false``, but it never wrote
    the probability itself into the row. A row that says only "not
    deterministic" cannot be turned into an expected yield, so the observed
    probability must be preserved.

    The captured live Pyanodons catalog proves the effect: 2,624 of its
    products carried ``deterministic: false`` with no probability field at
    all, because the field was observed and then discarded.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = ADAPTER.read_text(encoding="utf-8")
        start = cls.source.index("local function normalized_parts(")
        end = cls.source.index("\n                        for i=first,last do", start)
        cls.lua_function = cls.source[start:end]

    def setUp(self):
        try:
            import lupa  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("lupa is not installed; the Lua contract cannot run")

    def normalize(
        self, products: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Run the real adapter normalizer over the given products.

        ``None`` means the adapter refused the product shape. The return
        type is explicit so that a caller can narrow it with a plain
        ``assert`` and keep the subscripted access type-checked.
        """
        import lupa

        program: str = (
            self.lua_function
            + "\n"
            + f"local products = {lua_value(list(products))}\n"
            + "local p = normalized_parts(products, 8, true)\n"
            + "return {p = p or false, rejected = (p == nil)}\n"
        )
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        result = lua.execute(program)
        data = cast(
            dict[str, Any],
            result if isinstance(result, dict) else dict(cast(Any, result)),
        )
        if bool(data["rejected"]):
            return None
        return cast(list[dict[str, Any]], data["p"])

    def test_an_independent_probability_is_preserved(self):
        """The observed probability must reach the row."""
        products = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "independent_probability": 0.25},
        ])
        self.assertIsNotNone(products, "a probabilistic product was dropped")
        assert products is not None
        self.assertEqual(products[1]["independent_probability"], 0.25)

    def test_an_independent_probability_still_marks_the_row_not_deterministic(self):
        """A probability below one means the amount is not guaranteed."""
        products = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "independent_probability": 0.25},
        ])
        self.assertIsNotNone(products)
        assert products is not None
        self.assertEqual(products[1]["deterministic"], False)

    def test_a_probability_of_one_keeps_the_row_deterministic(self):
        """A probability of one means the product always appears."""
        products = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "independent_probability": 1},
        ])
        self.assertIsNotNone(products)
        assert products is not None
        self.assertNotIn("deterministic", products[1])
        self.assertEqual(products[1]["independent_probability"], 1)

    def test_a_shared_probability_is_preserved(self):
        """The shared {min,max} definition must reach the row."""
        products = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "shared_probability": {"min": 0, "max": 0.3}},
        ])
        self.assertIsNotNone(products, "a shared-probability product was dropped")
        assert products is not None
        self.assertEqual(products[1]["shared_probability"]["min"], 0)
        self.assertEqual(products[1]["shared_probability"]["max"], 0.3)

    def test_a_shared_probability_below_one_marks_the_row_not_deterministic(self):
        """A shared probability below one means the amount is not guaranteed."""
        products = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "shared_probability": {"min": 0, "max": 0.3}},
        ])
        self.assertIsNotNone(products)
        assert products is not None
        self.assertEqual(products[1]["deterministic"], False)

    def test_the_quality_affect_flag_is_preserved(self):
        """``affected_by_quality`` decides whether quality changes the result."""
        products = self.normalize([
            {"name": "iron-plate", "type": "item", "amount": 1,
             "affected_by_quality": True},
        ])
        self.assertIsNotNone(products)
        assert products is not None
        self.assertIs(products[1]["affected_by_quality"], True)

    def test_the_probability_fields_match_the_verified_2123_api(self):
        """The accepted probability fields must exist in the 2.1.23 API."""
        import json

        data = json.loads(API.read_text(encoding="utf-8"))
        types = {t["name"]: t for t in data["types"]}

        def field_names(type_name: str) -> set[str]:
            names: set[str] = set()
            seen: set[str] = set()
            current: str | None = type_name
            while current and current in types and current not in seen:
                seen.add(current)
                proto = types[current]
                for prop in proto.get("properties", []):
                    names.add(prop.get("name"))
                current = proto.get("parent")
            return names

        # ProductPrototypeBase declares both probability fields, so both the
        # item and the fluid product prototypes inherit them.
        for field in ("independent_probability", "shared_probability"):
            self.assertIn(field, field_names("ProductPrototypeBase"))
            self.assertIn(field, field_names("ItemProductPrototype"))
            self.assertIn(field, field_names("FluidProductPrototype"))
            self.assertNotIn(field, field_names("ItemIngredientPrototype"))
            self.assertNotIn(field, field_names("FluidIngredientPrototype"))


class RecipeExclusionReportTests(unittest.TestCase):
    """A refused recipe must be reported with the reason that was observed.

    The adapter used to drop a recipe the bounded model could not represent
    without saying which one it dropped or why. The gap between the reported
    recipe total and the emitted rows could then only be counted, never
    explained. The page now carries the dropped names and the observed
    reason, so the gap can be classified instead of guessed.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = ADAPTER.read_text(encoding="utf-8")
        start = cls.source.index("local function normalized_parts(")
        end = cls.source.index("local excluded = {}", start)
        cls.lua_function = cls.source[start:end]

    def setUp(self):
        try:
            import lupa  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("lupa is not installed; the Lua contract cannot run")

    def verdict(self, **overrides: Any) -> tuple[bool, str]:
        """Return whether the adapter accepts the recipe, and why not."""
        import lupa

        recipe: dict[str, Any] = {
            "enabled": True, "hidden": False, "energy": 0.5,
            "category": "crafting", "categories": ["crafting"],
            "ingredients": [{"name": "iron-plate", "type": "item", "amount": 2}],
            "products": [{"name": "iron-gear-wheel", "type": "item", "amount": 1}],
        }
        recipe.update(overrides)
        program: str = (
            self.lua_function
            + "\n"
            + f"local recipe = {lua_value(recipe)}\n"
            + "local ingredients = normalized_parts(recipe.ingredients, 16, false)\n"
            + "local products = normalized_parts(recipe.products, 8, true)\n"
            + "local categories = {}\n"
            + "if type(recipe.categories) == 'table' then\n"
            + "  for i = 1, math.min(#recipe.categories, 8) do\n"
            + "    local entry = recipe.categories[i]\n"
            + "    if type(entry) ~= 'string' or #entry < 1 or #entry > 128 then\n"
            + "      categories = nil break\n"
            + "    end\n"
            + "    categories[#categories+1] = entry\n"
            + "  end\n"
            + "  if categories and #recipe.categories > #categories then categories = nil end\n"
            + "else categories = nil end\n"
            + "local category = categories and #categories > 0 and categories[1] or nil\n"
            + "local accepted = ingredients and products and #products > 0\n"
            + "  and type(recipe.energy) == 'number' and type(category) == 'string'\n"
            + "  and #category > 0 and #category <= 128 and recipe.energy > 0\n"
            + "  and recipe.energy == recipe.energy and recipe.energy ~= math.huge\n"
            + "local reason = exclusion_reason(recipe, ingredients, products,\n"
            + "  recipe.energy, category)\n"
            + "return {accepted = (accepted and 'yes' or 'no'),"
            + " reason = reason or 'NONE'}\n"
        )
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        result = lua.execute(program)
        data = cast(
            dict[str, Any],
            result if isinstance(result, dict) else dict(cast(Any, result)),
        )
        return data["accepted"] == "yes", str(data["reason"])

    def test_a_representable_recipe_is_not_excluded(self):
        accepted, _reason = self.verdict()
        self.assertTrue(accepted, "a representable recipe was refused")

    def test_an_unaccepted_field_is_named(self):
        accepted, reason = self.verdict(products=[
            {"name": "widget", "type": "item", "amount": 1, "mod_specific_field": 3}])
        self.assertFalse(accepted)
        self.assertEqual(reason, "unknown_field:mod_specific_field")

    def test_a_recipe_without_products_is_reported_as_such(self):
        accepted, reason = self.verdict(products=[])
        self.assertFalse(accepted)
        self.assertEqual(reason, "no_products")

    def test_a_recipe_without_a_crafting_time_is_reported_as_such(self):
        accepted, reason = self.verdict(energy=0)
        self.assertFalse(accepted)
        self.assertEqual(reason, "bad_crafting_time")

    def test_a_recipe_without_a_category_is_reported_as_such(self):
        accepted, reason = self.verdict(category=None, categories=[])
        self.assertFalse(accepted)
        self.assertEqual(reason, "no_category")

    def test_an_ingredient_that_consumes_nothing_is_reported_as_such(self):
        accepted, reason = self.verdict(ingredients=[
            {"name": "iron-plate", "type": "item", "amount": 0}])
        self.assertFalse(accepted)
        self.assertEqual(reason, "ingredient_shape:amount")

    def test_the_page_carries_the_excluded_entries(self):
        self.assertIn("excluded=excluded", self.source)
        self.assertIn("reason=exclusion_reason(", self.source)

    def test_the_validator_accepts_and_classifies_the_observed_report(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import classify_exclusions, validate_capabilities

        caps = {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player", "research": [],
            "enabled_content": ["base"], "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [{
                "name": "iron-gear-wheel", "enabled": True, "hidden": False,
                "simple": True, "category": "crafting", "crafting_time": 0.5,
                "ingredients": [{"type": "item", "name": "iron-plate", "amount": 2}],
                "products": [{"type": "item", "name": "iron-gear-wheel", "amount": 1}],
            }],
            "excluded": [
                {"name": "aaa-unknown", "reason": "unknown_field:mod_field"},
                {"name": "bbb-unknown", "reason": "unknown_field:mod_field"},
                {"name": "ccc-empty", "reason": "no_products"},
            ],
        }
        parsed = validate_capabilities(caps, "nauvis", 120)
        self.assertEqual(len(parsed["excluded"]), 3)
        groups = classify_exclusions(parsed["excluded"])
        self.assertEqual(list(groups["unknown_field:mod_field"]),
                         ["aaa-unknown", "bbb-unknown"])
        self.assertEqual(groups["no_products"], ["ccc-empty"])
        # Validating an already validated payload must not change it.
        again = validate_capabilities(parsed, "nauvis", 120)
        self.assertEqual(again["excluded"], parsed["excluded"])

    def test_a_malformed_exclusion_report_is_refused(self):
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_capabilities

        base = {
            "schema": 1, "tick": 120, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player", "research": [],
            "enabled_content": ["base"], "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
            "recipes": [],
        }
        for report in (
            [{"name": "a"}],
            [{"name": "a", "reason": ""}],
            [{"name": "a", "reason": "x", "extra": 1}],
            [{"name": "a", "reason": "x"}, {"name": "a", "reason": "y"}],
            [{"name": "a", "reason": 12}],
            "not-a-list",
        ):
            with self.subTest(report=report):
                with self.assertRaises(ValueError):
                    validate_capabilities(dict(base, excluded=report), "nauvis", 120)


if __name__ == "__main__":
    unittest.main()
