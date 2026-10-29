"""Analyse the live 2.1.23 R06 catalog rows that the sweep captured.

Read-only analysis of the evidence the live sweep produced. It answers the
questions the mission asks, using the OBSERVED rows only:

* how many recipes are declared, represented and excluded, and why;
* how many products carry independent_probability, shared_probability, an
  amount range or a quality flag;
* how the enabled recipes split by determinism;
* what the 2,623 enabled ``py-incineration`` recipes actually are;
* which crafting categories have an observed machine and which do not.

Nothing is inferred: a recipe is counted as probabilistic only when the
observed row carries the probability field.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"


def load(tag: str) -> tuple[dict, list]:
    report = json.loads((EVIDENCE / f"{tag}.json").read_text(encoding="utf-8"))
    rows = report.get("rows_payload") or []
    return report, rows


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "r06-live-sweep-005"
    report, rows = load(tag)
    identity = report.get("identity") or {}

    print(f"TAG={tag}")
    print(f"declared_total={identity.get('total_count')}")
    print(f"rows_collected={len(rows)}")
    print(f"excluded_reported={identity.get('excluded_count')}")
    print(f"machines_reported={identity.get('machines_count')}")
    print(f"catalog_status={identity.get('catalog_status')}")
    print(f"truncated={identity.get('truncated')}")
    print()

    excluded = (report.get("exclusions") or {}).get("sample") or []
    full_excluded = report.get("exclusion_rows") or excluded
    print("EXCLUSION REASONS (as reported by the backend):")
    for reason, count in Counter(e.get("reason") for e in full_excluded).items():
        print(f"   {reason}: {count}")
    print()

    enabled = [r for r in rows if r.get("enabled")]
    disabled = [r for r in rows if not r.get("enabled")]
    hidden = [r for r in rows if r.get("hidden")]
    print(f"enabled={len(enabled)} disabled={len(disabled)} hidden={len(hidden)}")
    print()

    # The determinism split, decided only by the observed PRODUCT fields.
    # The "deterministic" flag lives on a product, not on the recipe row.
    indep = shared = ranged = quality_flagged = 0
    deterministic_rows = 0
    non_deterministic_rows = 0
    probability_values: Counter = Counter()
    for row in rows:
        parts = list(row.get("products") or [])
        has_indep = any("independent_probability" in p for p in parts)
        has_shared = any("shared_probability" in p for p in parts)
        has_range = any("amount_min" in p or "amount_max" in p for p in parts)
        has_quality = any("affected_by_quality" in p for p in parts)
        indep += has_indep
        shared += has_shared
        ranged += has_range
        quality_flagged += has_quality
        for part in parts:
            if "independent_probability" in part:
                probability_values[part["independent_probability"]] += 1
        if any(p.get("deterministic") is False for p in parts):
            non_deterministic_rows += 1
        else:
            deterministic_rows += 1
    print(f"rows_with_independent_probability={indep}")
    print(f"rows_with_shared_probability={shared}")
    print(f"rows_with_amount_range={ranged}")
    print(f"rows_with_affected_by_quality={quality_flagged}")
    print(f"rows_with_all_products_deterministic={deterministic_rows}")
    print(f"rows_with_a_sub_certain_product={non_deterministic_rows}")
    print(f"independent_probability_values={dict(sorted(probability_values.items()))}")
    print()

    # The py-incineration focus.
    incineration = [r for r in rows
                    if "py-incineration" in (r.get("categories") or [])
                    or r.get("category") == "py-incineration"]
    inc_enabled = [r for r in incineration if r.get("enabled")]
    print(f"py_incineration_rows={len(incineration)} "
          f"enabled={len(inc_enabled)} disabled={len(incineration) - len(inc_enabled)}")
    if inc_enabled:
        product_counts = Counter(len(r.get("products") or []) for r in inc_enabled)
        print(f"   product_count_distribution={dict(sorted(product_counts.items()))}")
        with_prob = sum(
            1 for r in inc_enabled
            if any("independent_probability" in p or "shared_probability" in p
                   for p in (r.get("products") or [])))
        print(f"   enabled_with_probability_field={with_prob}")
        det_false = sum(1 for r in inc_enabled if r.get("deterministic") is False)
        print(f"   enabled_deterministic_false={det_false}")
        sample = inc_enabled[0]
        print("   sample_row=" + json.dumps({
            "name": sample.get("name"),
            "category": sample.get("category"),
            "categories": sample.get("categories"),
            "enabled": sample.get("enabled"),
            "crafting_time": sample.get("crafting_time"),
            "ingredients": sample.get("ingredients"),
            "products": sample.get("products"),
            "deterministic": sample.get("deterministic"),
        }, sort_keys=True)[:900])
    print()

    # The enabled recipes that a fixed-rate path could actually plan.
    enabled_single = [r for r in enabled
                      if len(r.get("products") or []) == 1]
    enabled_single_det = []
    enabled_single_prob = []
    for row in enabled_single:
        part = (row.get("products") or [{}])[0]
        if part.get("deterministic") is False:
            enabled_single_prob.append(row)
        else:
            enabled_single_det.append(row)
    print(f"enabled_single_product={len(enabled_single)}")
    print(f"enabled_single_product_certain={len(enabled_single_det)}")
    print(f"enabled_single_product_sub_certain={len(enabled_single_prob)}")
    print()

    # Machine coverage by crafting category, from the observed rows.
    category_counts: Counter = Counter()
    for row in enabled:
        for category in (row.get("categories") or [row.get("category")]):
            if category:
                category_counts[category] += 1
    print(f"distinct_enabled_crafting_categories={len(category_counts)}")
    print("top_10_enabled_categories="
          + json.dumps(dict(category_counts.most_common(10)), sort_keys=True))

    machines = (report.get("machines") or {}).get("rows") or []
    machine_categories: set = set()
    machine_with_speed = 0
    machine_with_energy = 0
    machine_with_fluid_boxes = 0
    for machine in machines:
        for category in machine.get("crafting_categories") or []:
            machine_categories.add(category)
        if machine.get("crafting_speed") is not None:
            machine_with_speed += 1
        if machine.get("energy_usage") is not None:
            machine_with_energy += 1
        if machine.get("fluid_boxes"):
            machine_with_fluid_boxes += 1
    covered = {c for c, n in category_counts.items() if c in machine_categories}
    uncovered = {c: n for c, n in category_counts.items()
                 if c not in machine_categories}
    print()
    print(f"machines_total={len(machines)}")
    print(f"machines_with_crafting_speed={machine_with_speed}")
    print(f"machines_with_energy_usage={machine_with_energy}")
    print(f"machines_with_fluid_boxes={machine_with_fluid_boxes}")
    print(f"distinct_machine_crafting_categories={len(machine_categories)}")
    print(f"enabled_categories_with_a_machine={len(covered)}")
    print(f"enabled_categories_without_a_machine={len(uncovered)}")
    print(f"enabled_recipes_in_covered_categories="
          f"{sum(n for c, n in category_counts.items() if c in machine_categories)}")
    print(f"enabled_recipes_in_uncovered_categories="
          f"{sum(uncovered.values())}")
    print("uncovered_categories_top_10="
          + json.dumps(dict(sorted(uncovered.items(),
                                   key=lambda kv: -kv[1])[:10]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
