"""Audit: classify recipe exclusions by omission reason.

Runs the *real* backend ``normalized_parts`` Lua function (extracted verbatim
from backend-safety/Tools/RecipeResearchAdapter.cs) against representative
Factorio 2.1.23 recipe shapes and reports which omission reason applies.

This is a read-only offline analysis. It does not touch Factorio.

Omission reasons observed in the adapter:
  * unknown_field      - a product/ingredient carries a real 2.1.23 field the
                         adapter does not accept, so the whole recipe is
                         dropped.
  * no_products       - the recipe has zero products.
  * ingredient_shape  - an ingredient is missing name/type/amount or consumes a
                         non-positive amount.
  * product_shape     - a product is missing name/type/amount or has a bad
                         amount.
  * no_category       - the recipe declares no usable crafting category.
  * bad_crafting_time - crafting time is missing, non-numeric or <= 0.
"""

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"

# Real 2.1.23 fields, taken from the offline prototype API:
# .local/factorio-api-offline/2.1.23/files/prototype-api.json
PRODUCT_ITEM_FIELDS = (
    "affected_by_quality",
    "always_fresh",
    "amount",
    "amount_max",
    "amount_min",
    "extra_count_fraction",
    "ignored_by_productivity",
    "ignored_by_stats",
    "name",
    "percent_spoiled",
    "quality_change",
    "quality_max",
    "quality_min",
    "reset_freshness_on_craft",
    "type",
    "independent_probability",
    "shared_probability",
    "show_details_in_recipe_tooltip",
)
PRODUCT_FLUID_FIELDS = (
    "amount",
    "amount_max",
    "amount_min",
    "fluidbox_index",
    "fluidbox_multiplier",
    "ignored_by_productivity",
    "ignored_by_stats",
    "name",
    "optional_fluidbox_indexes",
    "temperature",
    "type",
    "independent_probability",
    "shared_probability",
    "show_details_in_recipe_tooltip",
)
INGREDIENT_ITEM_FIELDS = (
    "amount",
    "ignored_by_stats",
    "name",
    "quality_change",
    "quality_max",
    "quality_min",
    "spoil_weight",
    "type",
)
INGREDIENT_FLUID_FIELDS = (
    "amount",
    "fluidbox_index",
    "fluidbox_multiplier",
    "ignored_by_stats",
    "maximum_temperature",
    "minimum_temperature",
    "name",
    "optional_fluidbox_indexes",
    "temperature",
    "type",
)

ADAPTER_ACCEPTS = {
    "name",
    "type",
    "amount",
    "affected_by_quality",
    "independent_probability",
    "shared_probability",
    "ignored_by_stats",
    "spoil_weight",
    "fluidbox_multiplier",
    "fluidbox_index",
    # Factorio 2.1.23 temperature fields (fluid only).
    "temperature",
    "minimum_temperature",
    "maximum_temperature",
    # Factorio 2.1.23 quality fields (item only).
    "quality_min",
    "quality_max",
    "quality_change",
    # Factorio 2.1.23 product quantity fields.
    "amount_min",
    "amount_max",
    "extra_count_fraction",
    # Factorio 2.1.23 productivity and freshness fields.
    "ignored_by_productivity",
    "always_fresh",
    "reset_freshness_on_craft",
    "percent_spoiled",
    # Factorio 2.1.23 display fields.
    "optional_fluidbox_indexes",
    "show_details_in_recipe_tooltip",
}


def extract_lua(content: str) -> str:
    """Extract the real normalized_parts function from the adapter source."""
    start = content.index("local function normalized_parts(")
    end = content.index("\n                        for i=first,last do", start)
    return content[start:end]


def lua_value(value: Any) -> str:
    """Render a Python value as a Lua literal."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, dict):
        parts = [f"[{lua_value(k)}]={lua_value(v)}" for k, v in value.items()]
        return "{" + ",".join(parts) + "}"
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if isinstance(value, set):
            items = sorted(items)
        return "{" + ",".join(lua_value(v) for v in items) + "}"
    raise TypeError(f"unsupported Lua literal: {value!r}")


def run_lua(program: str) -> Any:
    import lupa

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    return lua.execute(program)


def classify(parts: list[dict[str, Any]], is_product: bool) -> str:
    """Return the omission reason for a rejected part list."""
    for part in parts:
        for field in part:
            if field not in ADAPTER_ACCEPTS:
                return f"unknown_field:{field}"
        name = part.get("name")
        ptype = part.get("type")
        amount = part.get("amount")
        if not isinstance(name, str) or not 1 <= len(name) <= 128:
            return "part_shape:name"
        if ptype not in ("item", "fluid"):
            return "part_shape:type"
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            return "part_shape:amount"
        if is_product and amount < 0:
            return "product_shape:negative_amount"
        if not is_product and amount <= 0:
            return "ingredient_shape:non_positive_amount"
    return "unknown"


def classify_parts(products: list[dict[str, Any]],
                   ingredients: list[dict[str, Any]]) -> str:
    """Classify a rejected recipe from its product and ingredient lists.

    A product and an ingredient are checked with their own rules: a product
    may have a zero amount (a probabilistic output) but an ingredient may
    not, because an ingredient that consumes nothing is not a real
    ingredient.
    """
    reason = classify(products, True)
    if reason != "unknown":
        return reason
    return classify(ingredients, False)


#: The adapter's own part limits. A recipe with more parts than the limit
#: is dropped by the adapter before any part is inspected.
PRODUCT_LIMIT = 8
INGREDIENT_LIMIT = 16


def main() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    lua_fn = extract_lua(source)

    # Case matrix: (label, product part, ingredient part)
    cases: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []

    def add(label: str, product: dict[str, Any], ingredient: dict[str, Any] | None = None) -> None:
        cases.append((label, product, ingredient))

    def add_many(label: str, products: list[dict[str, Any]],
                 ingredients: list[dict[str, Any]] | None = None) -> None:
        """Add a case whose part list is longer than the adapter's limit."""
        cases.append((label, products, ingredients))  # type: ignore[arg-type]

    # Baseline: plain item product.
    add("baseline_item", {"name": "iron-plate", "type": "item", "amount": 1})
    # Baseline: fluid product with temperature.
    add(
        "fluid_product_temperature",
        {"name": "steam", "type": "fluid", "amount": 100, "temperature": 15},
    )
    # Baseline: fluid ingredient with temperature window.
    add(
        "fluid_ingredient_temperature_window",
        {"name": "water", "type": "fluid", "amount": 100},
        {"name": "steam", "type": "fluid", "amount": 50,
         "minimum_temperature": 15, "maximum_temperature": 100},
    )
    # Quantity range (mining-style products).
    add(
        "product_amount_range",
        {"name": "iron-ore", "type": "item", "amount": 1,
         "amount_min": 1, "amount_max": 3},
    )
    # Quality bounded results.
    add(
        "product_quality_bounds",
        {"name": "iron-plate", "type": "item", "amount": 1,
         "quality_min": "normal", "quality_max": "legendary"},
    )
    # Quality change.
    add(
        "product_quality_change",
        {"name": "iron-plate", "type": "item", "amount": 1, "quality_change": 1},
    )
    # Ingredient quality bounds.
    add(
        "ingredient_quality_bounds",
        {"name": "iron-plate", "type": "item", "amount": 1},
        {"name": "iron-ore", "type": "item", "amount": 1,
         "quality_min": "normal", "quality_max": "rare"},
    )
    # Extra count fraction (probabilistic extra output).
    add(
        "product_extra_count_fraction",
        {"name": "iron-plate", "type": "item", "amount": 1,
         "extra_count_fraction": 0.5},
    )
    # Ignored by productivity.
    add(
        "product_ignored_by_productivity",
        {"name": "iron-plate", "type": "item", "amount": 1,
         "ignored_by_productivity": 1},
    )
    # Percent spoiled.
    add(
        "product_percent_spoiled",
        {"name": "iron-plate", "type": "item", "amount": 1, "percent_spoiled": 0.5},
    )
    # Always fresh / reset freshness.
    add(
        "product_freshness_flags",
        {"name": "iron-plate", "type": "item", "amount": 1,
         "always_fresh": True, "reset_freshness_on_craft": True},
    )
    # Tooltip display flag.
    add(
        "product_tooltip_flag",
        {"name": "iron-plate", "type": "item", "amount": 1,
         "show_details_in_recipe_tooltip": True},
    )
    # Optional fluidbox indexes.
    add(
        "fluid_optional_fluidbox_indexes",
        {"name": "steam", "type": "fluid", "amount": 100,
         "optional_fluidbox_indexes": {1, 2}},
    )
    # --- the shapes that the adapter's limits can reject ------------------
    # More products than the adapter's limit of 8.
    add_many(
        "product_count_over_limit",
        [{"name": f"plate-{index}", "type": "item", "amount": 1}
         for index in range(PRODUCT_LIMIT + 1)],
    )
    # More ingredients than the adapter's limit of 16.
    add_many(
        "ingredient_count_over_limit",
        [{"name": "iron-plate", "type": "item", "amount": 1}],
        [{"name": f"ore-{index}", "type": "item", "amount": 1}
         for index in range(INGREDIENT_LIMIT + 1)],
    )
    # Exactly at the limits is still accepted.
    add_many(
        "product_count_at_limit",
        [{"name": f"plate-{index}", "type": "item", "amount": 1}
         for index in range(PRODUCT_LIMIT)],
    )
    # A product whose type is neither item nor fluid.
    add(
        "product_unsupported_type",
        {"name": "custom", "type": "virtual", "amount": 1},
    )
    # An ingredient whose type is neither item nor fluid.
    add(
        "ingredient_unsupported_type",
        {"name": "iron-plate", "type": "item", "amount": 1},
        {"name": "custom", "type": "virtual", "amount": 1},
    )
    # A product whose amount is not a number.
    add(
        "product_non_numeric_amount",
        {"name": "iron-plate", "type": "item", "amount": "1"},
    )
    # An ingredient whose amount is not a number.
    add(
        "ingredient_non_numeric_amount",
        {"name": "iron-plate", "type": "item", "amount": 1},
        {"name": "iron-ore", "type": "item", "amount": "1"},
    )
    # An ingredient that consumes nothing.
    add(
        "ingredient_zero_amount",
        {"name": "iron-plate", "type": "item", "amount": 1},
        {"name": "iron-ore", "type": "item", "amount": 0},
    )

    program_template = (
        lua_fn
        + "\n"
        + "local products = __PRODUCTS__\n"
        + "local ingredients = __INGREDIENTS__\n"
        + "local p = normalized_parts(products, 8, true)\n"
        + "local i = normalized_parts(ingredients, 16, false)\n"
        + "return {p=p,i=i}\n"
    )

    print("=" * 78)
    print("RECIPE EXCLUSION AUDIT - real adapter normalized_parts vs 2.1.23 shapes")
    print("=" * 78)
    results = []
    for label, product, ingredient in cases:
        products = product if isinstance(product, list) else [product]
        ingredients = (
            ingredient if isinstance(ingredient, list)
            else ([ingredient] if ingredient else [])
        )
        program = program_template.replace(
            "__PRODUCTS__", lua_value(products)
        ).replace(
            "__INGREDIENTS__", lua_value(ingredients)
        )
        out = run_lua(program)
        accepted = out["p"] is not None and out["i"] is not None
        if accepted:
            reason = "ACCEPTED"
        elif len(products) > PRODUCT_LIMIT:
            reason = f"product_count_over_limit:{len(products)}>{PRODUCT_LIMIT}"
        elif len(ingredients) > INGREDIENT_LIMIT:
            reason = f"ingredient_count_over_limit:{len(ingredients)}>{INGREDIENT_LIMIT}"
        else:
            reason = classify_parts(products, ingredients)
        results.append((label, accepted, reason))
        print(f"  {label:42s} {'ACCEPTED' if accepted else 'REJECTED':9s} {'' if accepted else reason}")

    rejected = [r for r in results if not r[1]]
    print()
    print(f"TOTAL CASES: {len(results)}   ACCEPTED: {len(results) - len(rejected)}   REJECTED: {len(rejected)}")
    print()
    print("OMISSION REASON GROUPS:")
    groups: dict[str, list[str]] = {}
    for label, _accepted, reason in rejected:
        groups.setdefault(reason, []).append(label)
    for reason in sorted(groups):
        print(f"  {reason}  ({len(groups[reason])})")
        for label in groups[reason]:
            print(f"      - {label}")

    print()
    print("AUTHORITATIVE 2.1.23 FIELDS STILL REJECTED BY THE ADAPTER:")
    all_fields = sorted(
        set(PRODUCT_ITEM_FIELDS)
        | set(PRODUCT_FLUID_FIELDS)
        | set(INGREDIENT_ITEM_FIELDS)
        | set(INGREDIENT_FLUID_FIELDS)
    )
    for name in all_fields:
        if name not in ADAPTER_ACCEPTS:
            owner = []
            if name in PRODUCT_ITEM_FIELDS:
                owner.append("ItemProduct")
            if name in PRODUCT_FLUID_FIELDS:
                owner.append("FluidProduct")
            if name in INGREDIENT_ITEM_FIELDS:
                owner.append("ItemIngredient")
            if name in INGREDIENT_FLUID_FIELDS:
                owner.append("FluidIngredient")
            print(f"  - {name:32s} {','.join(owner)}")


if __name__ == "__main__":
    main()
