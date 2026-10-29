"""Deterministic offline benchmark of the catalog, search and machine paths.

The benchmark measures the read-only catalog path that the dashboard and
the planner use:

* validating a capability snapshot that carries recipes, excluded rows and
  crafting machines;
* building the recipe model that the search box filters;
* running the recipe search itself;
* planning one recipe against the observed machines.

It runs over two inputs:

* **SYNTHETIC** catalogs of 1,000, 5,000 and 10,000 recipes that have the
  shape of a large modpack. They are not Pyanodons recipe data.
* **OBSERVED** rows captured from the live Pyanodons run, when the captured
  evidence is present on this machine. Those rows are real observed
  recipe data; the machines that go with them are still SYNTHETIC, because
  the captured evidence predates the machine report.

No Factorio process, save, RCON command or external service is accessed.
"""

from __future__ import annotations

import json
import sys
import tracemalloc
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from read_only_planning import (  # noqa: E402
    classify_exclusions,
    machine_options,
    plan_recipe_production,
    validate_capabilities,
)

EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"
OBSERVED_ROWS = EVIDENCE / "r06-final-int-b-catalog-rows.json"

# The recipe categories the synthetic catalog uses. They are ordinary names;
# the benchmark never names a mod.
CATEGORIES = ("crafting", "smelting", "chemistry", "nano", "organic")


def synthetic_recipe(index: int) -> dict:
    """Return one synthetic recipe row with the shape of a modpack row."""
    category = CATEGORIES[index % len(CATEGORIES)]
    return {
        "name": f"synthetic-recipe-{index:06d}",
        "enabled": index % 17 != 0,
        "hidden": index % 53 == 0,
        "simple": index % 17 != 0 and index % 53 != 0,
        "category": category,
        "categories": [category],
        "crafting_time": 0.5 + (index % 40) * 0.25,
        "ingredients": [
            {"name": f"synthetic-input-{index % 512:04d}", "type": "item", "amount": 2},
            {"name": f"synthetic-input-{(index + 7) % 512:04d}", "type": "item", "amount": 1},
        ],
        "products": [
            {"name": f"synthetic-output-{index % 1024:05d}", "type": "item", "amount": 1},
        ],
    }


def synthetic_machine(index: int) -> dict:
    """Return one synthetic machine row."""
    return {
        "name": f"synthetic-machine-{index:04d}",
        "crafting_categories": [CATEGORIES[index % len(CATEGORIES)]],
        "crafting_speed": 0.5 + (index % 8) * 0.25,
        "energy_usage": 90000 + (index % 16) * 15000,
        "module_slots": 2 + (index % 4),
    }


def synthetic_catalog(count: int) -> dict:
    """Return a capability snapshot with ``count`` synthetic recipes."""
    return {
        "schema": 1, "tick": 120, "surface": "nauvis",
        "game_version": "2.1.23", "force": "player",
        "research": ["automation"], "enabled_content": ["base"],
        "truncated": False,
        "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
        "recipes": [synthetic_recipe(index) for index in range(count)],
        "excluded": [
            {"name": f"synthetic-excluded-{index:05d}",
             "reason": "unknown_field:mod_specific_field"}
            for index in range(max(1, count // 50))
        ],
        "machines": [synthetic_machine(index) for index in range(64)],
    }


def observed_catalog() -> dict | None:
    """Return a capability snapshot built from the captured observed rows."""
    if not OBSERVED_ROWS.is_file():
        return None
    rows = json.loads(OBSERVED_ROWS.read_text(encoding="utf-8"))
    recipes = []
    for name in sorted(rows):
        row = rows[name]
        recipes.append({
            "name": row["name"],
            "enabled": row["enabled"],
            "hidden": row["hidden"],
            "simple": row["simple"],
            "category": row["category"],
            "categories": row.get("categories") or [row["category"]],
            "crafting_time": row["crafting_time"],
            "ingredients": row["ingredients"],
            "products": row["products"],
        })
    return {
        "schema": 1, "tick": 120, "surface": "nauvis",
        "game_version": "2.1.23", "force": "player",
        "research": ["automation"], "enabled_content": ["base"],
        "truncated": False,
        "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
        "recipes": recipes,
        "excluded": [],
        "machines": [synthetic_machine(index) for index in range(64)],
    }


def measure(catalog: dict, *, label: str, search_terms=("synthetic", "recipe-0001")):
    """Measure the catalog, search and production-math paths."""
    report: dict = {"label": label, "recipes": len(catalog["recipes"])}
    tracemalloc.start()
    started = perf_counter()
    parsed = validate_capabilities(catalog, "nauvis", 120)
    report["validate_seconds"] = perf_counter() - started

    started = perf_counter()
    rows = []
    for recipe in parsed["recipes"]:
        ingredients = " ".join(part["name"] for part in recipe["ingredients"])
        rows.append({
            "name": recipe["name"],
            "category": recipe["category"],
            "search": " ".join([
                recipe["name"], recipe["category"], ingredients,
                *(part["name"] for part in recipe["products"]),
            ]).casefold(),
        })
    report["model_seconds"] = perf_counter() - started

    for index, term in enumerate(search_terms):
        query = term.casefold()
        started = perf_counter()
        matches = sum(1 for row in rows if query in row["search"])
        report[f"search_{index}_seconds"] = perf_counter() - started
        report[f"search_{index}_matches"] = matches
        report[f"search_{index}_term"] = term

    started = perf_counter()
    options = machine_options(parsed["recipes"], parsed["machines"],
                              parsed["recipes"][0]["category"])
    report["machine_lookup_seconds"] = perf_counter() - started
    report["machine_options"] = len(options)

    # The plan step needs a recipe the game reports as enabled, with a single
    # deterministic product. The observed catalog contains many stochastic
    # and multi-output recipes; those are counted, not planned.
    plannable = [
        r for r in parsed["recipes"]
        if r["enabled"] and len(r["products"]) == 1
        and r["products"][0].get("deterministic") is not False
    ]
    report["plannable_recipes"] = len(plannable)
    if not plannable:
        report["plan_status"] = "no plannable recipe"
    else:
        started = perf_counter()
        plan = plan_recipe_production(parsed, plannable[0]["name"],
                                      target_per_second=1.0)
        report["plan_seconds"] = perf_counter() - started
        report["plan_status"] = plan["status"]

    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report["peak_bytes"] = peak
    report["excluded_rows"] = len(parsed["excluded"])
    report["exclusion_reasons"] = {
        reason: len(names)
        for reason, names in classify_exclusions(parsed["excluded"]).items()
    }
    report["plannable_reasons"] = planability_reasons(parsed["recipes"])
    return report


def planability_reasons(recipes) -> dict:
    """Return why the observed recipes are or are not plannable.

    The reason a recipe cannot be planned is a property of the observed
    data, not an assumption. Disabled recipes are research-locked, a
    stochastic product has no fixed yield, and a multi-output recipe has no
    single target rate.
    """
    counts: dict[str, int] = {}
    for recipe in recipes:
        if not recipe["enabled"]:
            reason = "disabled"
        elif len(recipe["products"]) != 1:
            reason = "multi_output"
        elif recipe["products"][0].get("deterministic") is False:
            reason = "stochastic_product"
        elif any(part["type"] != "item" for part in recipe["ingredients"]):
            reason = "fluid_ingredient"
        elif recipe["products"][0]["type"] != "item":
            reason = "fluid_product"
        else:
            reason = "plannable"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def run_all() -> list[dict]:
    """Measure every input and return the reports."""
    reports = []
    for count in (1000, 5000, 10000):
        reports.append(measure(synthetic_catalog(count),
                                label=f"SYNTHETIC-{count}"))
    observed = observed_catalog()
    if observed is not None:
        reports.append(measure(observed, label="OBSERVED-PYANODONS",
                                search_terms=("nano", "photonic", "silver")))
    else:
        reports.append({"label": "OBSERVED-PYANODONS",
                        "status": "not captured on this machine"})
    return reports


def main() -> int:
    reports = run_all()
    print(json.dumps(reports, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
