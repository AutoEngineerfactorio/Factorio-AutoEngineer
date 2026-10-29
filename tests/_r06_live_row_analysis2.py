"""Detail the live recipes that a fixed-rate path could actually plan.

Read-only analysis of the live sweep evidence. It answers two questions with
observed values only:

* which enabled recipes have a certain, single, item-or-fluid product, and
  which crafting category they belong to;
* why the observed machines carry no crafting speed, and what the observed
  crafting categories actually are.

It also reports the machine's own energy and fluid-box coverage, because a
machine without an observed speed is still a machine the planner must be able
to name.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "r06-live-sweep-006"
    report = json.loads((EVIDENCE / f"{tag}.json").read_text(encoding="utf-8"))
    rows = report.get("rows_payload") or []
    machines = (report.get("machines") or {}).get("rows") or []

    enabled = [r for r in rows if r.get("enabled")]
    certain = []
    for row in enabled:
        parts = row.get("products") or []
        if len(parts) != 1:
            continue
        part = parts[0]
        if part.get("deterministic") is False:
            continue
        certain.append(row)

    print(f"enabled={len(enabled)} certain_single_product={len(certain)}")
    print()

    print("THE CERTAIN ENABLED RECIPES:")
    for row in sorted(certain, key=lambda r: r.get("name") or ""):
        part = (row.get("products") or [{}])[0]
        print(f"   {row.get('name')!r} category={row.get('category')!r} "
              f"time={row.get('crafting_time')} "
              f"product={part.get('name')!r}/{part.get('type')} "
              f"amount={part.get('amount')}")
    print()

    categories = Counter(r.get("category") for r in certain)
    print("certain_recipes_by_category=" + json.dumps(dict(categories),
                                                     sort_keys=True))
    print()

    # The observed machine picture.
    print("OBSERVED MACHINE SUMMARY:")
    print(f"   machines={len(machines)}")
    print(f"   with_crafting_speed="
          f"{sum(1 for m in machines if m.get('crafting_speed') is not None)}")
    print(f"   with_energy_usage="
          f"{sum(1 for m in machines if m.get('energy_usage') is not None)}")
    print(f"   with_module_slots="
          f"{sum(1 for m in machines if m.get('module_slots') is not None)}")
    print(f"   with_allowed_effects="
          f"{sum(1 for m in machines if m.get('allowed_effects') is not None)}")
    print(f"   with_allowed_module_categories="
          f"{sum(1 for m in machines if m.get('allowed_module_categories') is not None)}")
    print(f"   with_fluid_boxes="
          f"{sum(1 for m in machines if m.get('fluid_boxes') is not None)}")
    print()

    # Which crafting categories DO have a machine, and which machines.
    machine_by_category: dict[str, list[str]] = {}
    for machine in machines:
        for category in machine.get("crafting_categories") or []:
            machine_by_category.setdefault(category, []).append(machine["name"])

    for category in sorted(categories):
        names = machine_by_category.get(category, [])
        print(f"   category {category!r}: {len(names)} machine(s)")
        for name in sorted(names)[:4]:
            print(f"       {name}")
    print()

    # The categories with no machine at all.
    all_categories = Counter()
    for row in enabled:
        for category in (row.get("categories") or [row.get("category")]):
            if category:
                all_categories[category] += 1
    missing = {c: n for c, n in all_categories.items()
               if c not in machine_by_category}
    print("ENABLED CATEGORIES WITH NO OBSERVED MACHINE: "
          + json.dumps(missing, sort_keys=True))
    print()

    # A machine that can actually run a "crafting" recipe.
    crafting = machine_by_category.get("crafting", [])
    print(f"machines_for_crafting={len(crafting)}")
    for name in sorted(crafting)[:6]:
        machine = next(m for m in machines if m["name"] == name)
        print(f"   {name}: energy={machine.get('energy_usage')} "
              f"speed={machine.get('crafting_speed')} "
              f"effects={machine.get('allowed_effects')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
