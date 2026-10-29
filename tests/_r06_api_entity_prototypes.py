"""Locate the 2.1.23 runtime declarations of the machine fields.

Read-only inspection of the pinned offline 2.1.23 API archive. The live probe
showed ``crafting_speed`` and ``module_slots`` are ``nil`` on the runtime
prototype object, so this script reports which runtime class DOES declare
those names, if any.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / ".local" / "factorio-api-offline" / "2.1.23" / "files"

WANTED = ("crafting_speed", "module_slots", "allowed_module_categories",
          "crafting_categories", "energy_usage", "fluidbox_prototypes")


def class_entries(document: dict) -> list:
    classes = document.get("classes") or []
    if isinstance(classes, dict):
        return list(classes.values())
    return [c for c in classes if isinstance(c, dict)]


def read_type(attribute: dict) -> str:
    value = attribute.get("read_type")
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def main() -> int:
    runtime = json.loads((FILES / "runtime-api.json").read_text(encoding="utf-8"))
    by_name = {e.get("name"): e for e in class_entries(runtime)}

    for wanted in WANTED:
        owners = []
        for name, entry in sorted(by_name.items()):
            for attribute in entry.get("attributes") or []:
                if isinstance(attribute, dict) and attribute.get("name") == wanted:
                    owners.append(f"{name} ({read_type(attribute)})")
        print(f"== {wanted}")
        for owner in owners:
            print("   declared on:", owner)
        if not owners:
            print("   NOT DECLARED anywhere in runtime-api.json")

    # The entity prototype's own declared member list, so the real names are
    # visible next to the ones the adapter assumed.
    print()
    print("== LuaEntityPrototype members that relate to crafting/modules:")
    entity = by_name.get("LuaEntityPrototype") or {}
    for attribute in entity.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        name = str(attribute.get("name") or "")
        if ("craft" in name or "module" in name or "effect" in name
                or "fluidbox" in name or "speed" in name):
            print(f"   {name} : {read_type(attribute)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
