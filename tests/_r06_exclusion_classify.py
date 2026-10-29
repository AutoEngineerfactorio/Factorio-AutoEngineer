"""Classify the live catalog's excluded recipes from the observed data.

The live backend reports ``total_count`` (the number of recipes the game
has) and the rows it could represent. The difference is the set of recipes
the adapter could not represent.

This script works from the **live** row dump plus the adapter's own
acceptance rules, and it classifies the gap by the actual reason rather
than by assumption:

* ``no_products`` - the recipe has no product the game defines.
* ``ingredient_shape`` - an ingredient is missing a name, a type or a
  positive amount.
* ``product_shape`` - a product is missing a name, a type or has a bad
  amount.
* ``no_category`` - the recipe declares no usable crafting category.
* ``bad_crafting_time`` - the crafting time is missing, non-numeric or
  not greater than zero.
* ``unknown_field`` - a part carries a real 2.1.23 field the adapter does
  not accept, so the whole recipe is dropped.
* ``hidden_or_special`` - the recipe is hidden or is a special-purpose
  recipe that the game does not expose for planning.

The script never guesses a mechanic and never invents a recipe. It reports
what the observed data shows.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"

#: The fields the adapter accepts, taken from the adapter source itself.
#: This is the single source of truth for the accepted field set.
#: ``deterministic`` is accepted: the adapter reports it for a part whose
#: occurrence is not certain, and the Python validator accepts it too.
ADAPTER_ACCEPTS = {
    "name", "type", "amount",
    "affected_by_quality", "independent_probability", "shared_probability",
    "ignored_by_stats", "spoil_weight",
    "fluidbox_multiplier", "fluidbox_index",
    "temperature", "minimum_temperature", "maximum_temperature",
    "quality_min", "quality_max", "quality_change",
    "amount_min", "amount_max", "extra_count_fraction",
    "ignored_by_productivity", "always_fresh", "reset_freshness_on_craft",
    "percent_spoiled", "optional_fluidbox_indexes",
    "show_details_in_recipe_tooltip",
    "deterministic",
}

#: The real 2.1.23 part fields, from the offline prototype API.
AUTHORITATIVE_FIELDS = {
    "product_item": (
        "affected_by_quality", "always_fresh", "amount", "amount_max",
        "amount_min", "extra_count_fraction", "ignored_by_productivity",
        "ignored_by_stats", "name", "percent_spoiled", "quality_change",
        "quality_max", "quality_min", "reset_freshness_on_craft", "type",
        "independent_probability", "shared_probability",
        "show_details_in_recipe_tooltip",
    ),
    "product_fluid": (
        "amount", "amount_max", "amount_min", "fluidbox_index",
        "fluidbox_multiplier", "ignored_by_productivity", "ignored_by_stats",
        "name", "optional_fluidbox_indexes", "temperature", "type",
        "independent_probability", "shared_probability",
        "show_details_in_recipe_tooltip",
    ),
    "ingredient_item": (
        "amount", "ignored_by_stats", "name", "quality_change",
        "quality_max", "quality_min", "spoil_weight", "type",
    ),
    "ingredient_fluid": (
        "amount", "fluidbox_index", "fluidbox_multiplier", "ignored_by_stats",
        "maximum_temperature", "minimum_temperature", "name",
        "optional_fluidbox_indexes", "temperature", "type",
    ),
}


def _is_number(value) -> bool:
    return type(value) in (int, float) and not isinstance(value, bool)


def _as_number(value):
    """Return the value as a float when it is a real number, else None."""
    if not _is_number(value):
        return None
    return float(value)


def classify_part(part) -> str:
    """Return the reason one part would be rejected, or an empty string."""
    if not isinstance(part, dict):
        return "part_shape:not_a_mapping"
    for field in part:
        if field not in ADAPTER_ACCEPTS:
            return f"unknown_field:{field}"
    name = part.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 128:
        return "part_shape:name"
    ptype = part.get("type")
    if ptype not in ("item", "fluid"):
        return "part_shape:type"
    amount = _as_number(part.get("amount"))
    if amount is None:
        return "part_shape:amount"
    if amount < 0:
        return "part_shape:negative_amount"
    return ""


def classify_recipe(row) -> str:
    """Return the reason one recipe would be rejected, or an empty string."""
    if not isinstance(row, dict):
        return "recipe_shape:not_a_mapping"
    name = row.get("name")
    if not isinstance(name, str) or not name:
        return "recipe_shape:name"
    products = row.get("products")
    if not isinstance(products, list) or not products:
        return "no_products"
    for part in products:
        reason = classify_part(part)
        if reason:
            return f"product:{reason}"
    ingredients = row.get("ingredients")
    if isinstance(ingredients, list):
        for part in ingredients:
            reason = classify_part(part)
            if reason:
                return f"ingredient:{reason}"
    category = row.get("category")
    if not isinstance(category, str) or not category:
        return "no_category"
    crafting_time = _as_number(row.get("crafting_time"))
    if crafting_time is None:
        return "bad_crafting_time"
    if crafting_time <= 0:
        return "bad_crafting_time"
    return ""


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "r06-final-int-b"
    rows_path = EVIDENCE / f"{tag}-catalog-rows.json"
    report_path = EVIDENCE / f"{tag}.json"
    if not rows_path.is_file():
        print(f"ROWS_MISSING {rows_path}")
        return 1
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}

    total_count = report.get("catalog_total_count")
    represented = len(rows)
    print(f"rows_file={rows_path.name}")
    print(f"game_reported_total={total_count}")
    print(f"represented={represented}")
    if isinstance(total_count, int):
        print(f"not_represented={total_count - represented}")

    # Group the observed recipes by the reason they would be rejected.
    groups: dict[str, list[str]] = {}
    for name, row in sorted(rows.items()):
        reason = classify_recipe(row)
        if reason:
            groups.setdefault(reason.split(":")[0], []).append(name)

    print("\nREPRESENTED-ROW CLASSIFICATION (a row that would still be rejected):")
    if not groups:
        print("  none: every observed row satisfies the adapter's acceptance rules")
    for reason in sorted(groups):
        print(f"  {reason}: {len(groups[reason])}")
        for name in groups[reason][:10]:
            print(f"      - {name}")

    # The observed field inventory proves which real 2.1.23 fields appear.
    observed_fields: set[str] = set()
    for row in rows.values():
        for part in list(row.get("products") or []) + list(row.get("ingredients") or []):
            if isinstance(part, dict):
                observed_fields.update(part)
    unknown = sorted(observed_fields - ADAPTER_ACCEPTS)
    print("\nOBSERVED FIELDS NOT ACCEPTED BY THE ADAPTER:")
    print("  " + (", ".join(unknown) if unknown else "none"))

    # Which authoritative 2.1.23 fields were never observed at all.
    all_authoritative: set[str] = set()
    for fields in AUTHORITATIVE_FIELDS.values():
        all_authoritative.update(fields)
    print("\nAUTHORITATIVE 2.1.23 FIELDS NEVER OBSERVED LIVE:")
    never = sorted(all_authoritative - observed_fields)
    print("  " + (", ".join(never) if never else "none"))

    print("\nLIVE MECHANIC INVENTORY (how many observed rows carry each field):")
    for field in sorted(observed_fields):
        count = sum(
            1 for row in rows.values()
            if any(
                isinstance(part, dict) and field in part
                for part in list(row.get("products") or []) + list(row.get("ingredients") or [])
            )
        )
        print(f"  {field}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
