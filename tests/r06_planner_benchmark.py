"""Deterministic offline benchmark of the R06 planner over a large catalog.

The benchmark builds a synthetic catalog that has the *shape* of a large
modpack: many recipes, several crafting categories, fluid inputs and
outputs, probabilistic and ranged results, byproducts, alternative
pathways, research-locked recipes and a recycling cycle.

It measures the catalog path end to end - validation, feasibility, effective
yield and material planning - and reports the latency and the peak memory.

These are SYNTHETIC fixtures. They are not Pyanodons recipe data and they
are not gameplay certification. No Factorio process, save, RCON command or
external service is accessed.
"""

from __future__ import annotations

import json
import sys
import tracemalloc
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from read_only_planning import validate_capabilities  # noqa: E402
from recipe_material_planner import plan_product_materials  # noqa: E402

# The catalog bound the backend itself can address.
MAX_CATALOG_ENTRIES = 10000 * 16


def _recipe(
    name: str,
    *,
    ingredients: list[dict],
    products: list[dict],
    category: str = "crafting",
    crafting_time: float = 1.0,
    enabled: bool = True,
    hidden: bool = False,
    unlocks: list[dict] | None = None,
    categories: list[str] | None = None,
) -> dict:
    row = {
        "name": name,
        "enabled": enabled,
        "hidden": hidden,
        "simple": (
            enabled and not hidden and len(products) == 1
            and all(part["type"] == "item" for part in ingredients + products)
        ),
        "category": category,
        "crafting_time": crafting_time,
        "ingredients": ingredients,
        "products": products,
    }
    if unlocks is not None:
        row["unlock_technologies"] = unlocks
    if categories is not None:
        row["categories"] = categories
    return row


def _item(name: str, amount: float = 1) -> dict:
    return {"name": name, "type": "item", "amount": amount}


def _fluid(name: str, amount: float = 100) -> dict:
    return {"name": name, "type": "fluid", "amount": amount}


def build_catalog(size: int) -> dict:
    """Build a synthetic catalog of the given size.

    The catalog mixes the mechanics that a large modpack exercises: plain
    recipes, fluid recipes, ranged products, probabilistic products,
    spoiled products, byproducts, alternative pathways, research-locked
    recipes, nonstandard crafting categories and a recycling cycle.
    """
    if not 1 <= size <= 50000:
        raise ValueError("size must be between 1 and 50000")
    recipes = []
    for index in range(size):
        name = f"mod-recipe-{index:06}"
        ingredient = _item(f"mod-input-{index:06}")
        product = _item(name)
        category = "crafting"
        unlocks = None
        categories = None
        ingredients = [ingredient]
        products = [product]
        shape = index % 10
        if shape == 1:
            # A fluid recipe with a temperature requirement.
            ingredients = [{**_fluid("steam"), "minimum_temperature": 15,
                            "maximum_temperature": 100}]
            products = [{**_fluid(name), "temperature": 15}]
            category = "chemistry"
            categories = ["chemistry", "py-incineration"]
        elif shape == 2:
            # A ranged result.
            products = [{**product, "amount_min": 1, "amount_max": 3}]
        elif shape == 3:
            # A probabilistic result.
            products = [{**product, "independent_probability": 0.25}]
        elif shape == 4:
            # A spoiled result with a byproduct.
            products = [{**product, "percent_spoiled": 0.25},
                        _item(f"mod-byproduct-{index:06}", 0.5)]
        elif shape == 5:
            # A quality-bounded result.
            products = [{**product, "quality_min": "normal",
                         "quality_max": "legendary"}]
        elif shape == 6:
            # A research-locked recipe.
            unlocks = [{"name": "mod-technology", "researched": False,
                        "enabled": True}]
        elif shape == 7:
            # A productivity-restricted result.
            products = [{**product, "ignored_by_productivity": 1}]
        elif shape == 8:
            # An extra fractional output.
            products = [{**product, "extra_count_fraction": 0.5}]
        elif shape == 9 and index > 0:
            # A recycling cycle: this recipe consumes the previous one.
            ingredients = [ingredient, _item(f"mod-recipe-{index - 1:06}", 1)]
        recipes.append(_recipe(
            name, ingredients=ingredients, products=products,
            category=category, crafting_time=1.0 + (index % 7) * 0.5,
            unlocks=unlocks, categories=categories,
        ))
    # A target that every plain recipe can feed.
    recipes.append(_recipe(
        "mod-target", ingredients=[_item("mod-recipe-000000")],
        products=[_item("mod-target")],
    ))
    return {
        "schema": 1,
        "tick": 120,
        "surface": "nauvis",
        "game_version": "2.1.23",
        "force": "player",
        "research": ["automation"],
        "enabled_content": ["base"],
        "truncated": False,
        "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
        "recipes": recipes,
    }


def _intelligence(capabilities: dict) -> dict:
    """Wrap a raw capability snapshot in the intelligence envelope."""
    return {
        "status": "ok",
        "tick": 120,
        "surface": "nauvis",
        "position": {"x": 0, "y": 0},
        "inventory": [],
        "inventory_available": True,
        "truncated": False,
        "capabilities": capabilities,
        "catalog_status": {"status": "assembled"},
        "planner_ready": True,
    }


def run_benchmark(size: int) -> dict:
    """Measure the catalog path over a synthetic catalog of the given size."""
    tracemalloc.start()
    try:
        build_start = perf_counter()
        raw = build_catalog(size)
        build_ms = (perf_counter() - build_start) * 1000

        validate_start = perf_counter()
        capabilities = validate_capabilities(raw, "nauvis", 120)
        validate_ms = (perf_counter() - validate_start) * 1000

        intelligence = _intelligence(capabilities)

        plan_start = perf_counter()
        plan = plan_product_materials(intelligence, "item", "mod-target", 1)
        plan_ms = (perf_counter() - plan_start) * 1000

        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    return {
        "dataset": "synthetic-modpack-catalog-v1",
        "actual_pyanodons_data": False,
        "recipe_count": len(raw["recipes"]),
        "validated_recipes": len(capabilities["recipes"]),
        "catalog_build_ms": round(build_ms, 3),
        "validation_ms": round(validate_ms, 3),
        "plan_ms": round(plan_ms, 3),
        "peak_memory_mib": round(peak_bytes / (1024 ** 2), 3),
        "plan_status": plan["status"],
        "selected_recipes": len(plan["selected_recipes"]),
        "unresolved_rows": len(plan["unresolved"]),
        "unsupported_mechanics": len(plan["unsupported_mechanics"]),
        "feasibility_rows": len(plan["recipe_feasibility"]),
        "python": sys.version.split()[0],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000])
    options = parser.parse_args()
    print(json.dumps([run_benchmark(size) for size in options.sizes], indent=2))


if __name__ == "__main__":
    main()
