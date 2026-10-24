"""Read-only capability/ledger/planning bridge with explicit incomplete states.

Uses only already received, validated display data. No MCP, RCON, gameplay,
model call, filesystem state or generated permissions. A partial catalog page
is observable but never certifies planner readiness.
"""
import hashlib
import json
import math
import re
import time
from typing import Any

from capability_snapshot import assess_capability_snapshot
from mechanics_coverage import (
    compute_ledger_summary,
    create_mechanic_entry,
    create_mechanics_ledger,
)
from production_solver import MaterialInput, ProductionSolver, create_machine, create_recipe

# The sole supported development and testing game version. Qualification here
# enables read-only catalog preview only; it is not evidence that a
# runtime/backend combination passed live acceptance. Any other patch version
# requires a deliberate compatibility review before it may be qualified.
QUALIFIED_GAME_VERSIONS = frozenset({"2.1.23"})
QUALIFIED_CONTENT = frozenset({"base", "core", "autoengineer-input"})


def profile_qualified(caps):
    return (caps.get("game_version") in QUALIFIED_GAME_VERSIONS
            and "base" in caps.get("enabled_content", [])
            and set(caps["enabled_content"]).issubset(QUALIFIED_CONTENT))


def bounded_name(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("Invalid capability name")
    return value


def bounded_names(value, limit):
    if isinstance(value, dict) and not value:
        value = []
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("Unbounded capability name list")
    names = [bounded_name(x) for x in value]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate capability name")
    return sorted(names)


def positive(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid recipe/machine quantity")
    return float(value)


def validate_capabilities(raw, surface, tick):
    """Bound optional *same-tick* backend metadata; no inferred recipes.

    The simple flag is a separately verified one-item-product recipe contract.
    Complex probabilities, temperature, fluid, catalyst, module, quality and
    recycle semantics MUST NOT be silently treated as simple.
    """
    if (not isinstance(raw, dict) or type(raw.get("schema")) is not int
            or raw["schema"] != 1 or type(raw.get("tick")) is not int
            or raw["tick"] != tick or raw.get("surface") != surface
            or type(raw.get("truncated")) is not bool):
        raise ValueError("Invalid/stale capability envelope")
    version = bounded_name(raw.get("game_version"))
    if not version.startswith("2."):
        raise ValueError("Unqualified Factorio game version")
    research = bounded_names(raw.get("research"), 256)
    enabled_content = bounded_names(raw.get("enabled_content"), 32)
    recipes = raw.get("recipes")
    if isinstance(recipes, dict) and not recipes:
        recipes = []
    if not isinstance(recipes, list) or len(recipes) > 10000:
        raise ValueError("Missing or unbounded recipe catalog")
    source_fingerprint = raw.get("source_fingerprint")
    if (source_fingerprint is not None
            and (not isinstance(source_fingerprint, str)
                 or re.fullmatch(r"poly31x131-v1:[0-9]{10}-[0-9]{10}", source_fingerprint) is None)):
        raise ValueError("Invalid source fingerprint")
    seen = set()
    parsed = []
    for rec in recipes:
        if not isinstance(rec, dict):
            raise ValueError("Invalid recipe")
        # Unknown fields may contain probabilities, temperature, quality or
        # other gameplay requirements: fail closed rather than dropping them.
        base_fields = {
            "name", "enabled", "hidden", "simple", "category",
            "crafting_time", "ingredients", "products",
        }
        # Factorio 2.1 recipes may declare several categories and may produce a
        # stochastic amount. Both are bounded and observed, so they are accepted
        # explicitly; every other unknown field still fails closed.
        optional_fields = {"unlock_technologies", "categories"}
        if not base_fields <= set(rec) <= (base_fields | optional_fields):
            raise ValueError("Unsupported/ambiguous recipe fields")
        name = bounded_name(rec.get("name"))
        category = bounded_name(rec.get("category"))
        if (name in seen or type(rec.get("enabled")) is not bool
                or type(rec.get("hidden")) is not bool or type(rec.get("simple")) is not bool
                or rec["simple"] and (not rec["enabled"] or rec["hidden"])):
            raise ValueError("Duplicate/ambiguous recipe")
        seen.add(name)
        items, products = rec.get("ingredients"), rec.get("products")
        if isinstance(items, dict) and not items:
            items = []
        if isinstance(products, dict) and not products:
            products = []
        if (not isinstance(items, list) or len(items) > 16
                or not isinstance(products, list) or not 1 <= len(products) <= 8):
            raise ValueError("Unbounded ingredient/product list")

        def part(data):
            if not isinstance(data, dict):
                raise ValueError("Unsupported item/fluid attributes")
            allowed = {"name", "type", "amount"} | (
                {"deterministic"} if "deterministic" in data else set()
            )
            if (set(data) != allowed or data.get("type") not in ("item", "fluid")):
                raise ValueError("Unsupported item/fluid attributes")
            parsed_part = {"name": bounded_name(data.get("name")),
                           "type": data["type"], "amount": positive(data.get("amount"))}
            if "deterministic" in data:
                if type(data["deterministic"]) is not bool:
                    raise ValueError("Invalid product determinism marker")
                parsed_part["deterministic"] = data["deterministic"]
            return parsed_part

        categories = None
        if "categories" in rec:
            raw_categories = rec["categories"]
            if not isinstance(raw_categories, list) or not 1 <= len(raw_categories) <= 8:
                raise ValueError("Invalid recipe category list")
            categories = [bounded_name(value) for value in raw_categories]
            if len(set(categories)) != len(categories):
                raise ValueError("Duplicate recipe category")
            if categories[0] != category:
                raise ValueError("Recipe category list disagrees with the primary category")

        unlock_technologies = None
        if "unlock_technologies" in rec:
            raw_unlocks = rec["unlock_technologies"]
            if not isinstance(raw_unlocks, list) or len(raw_unlocks) > 8:
                raise ValueError("Invalid recipe technology unlock list")
            unlock_technologies = []
            seen_unlocks = set()
            for unlock in raw_unlocks:
                if (not isinstance(unlock, dict)
                        or set(unlock) != {"name", "researched", "enabled"}
                        or type(unlock.get("researched")) is not bool
                        or type(unlock.get("enabled")) is not bool):
                    raise ValueError("Invalid recipe technology unlock")
                unlock_name = bounded_name(unlock["name"])
                if unlock_name in seen_unlocks:
                    raise ValueError("Duplicate recipe technology unlock")
                seen_unlocks.add(unlock_name)
                unlock_technologies.append({
                    "name": unlock_name,
                    "researched": unlock["researched"],
                    "enabled": unlock["enabled"],
                })
            if unlock_technologies != sorted(
                unlock_technologies, key=lambda item: item["name"]
            ):
                raise ValueError("Recipe technology unlocks are not deterministically ordered")

        parsed.append({
            "name": name, "enabled": rec["enabled"], "hidden": rec["hidden"],
            "simple": rec["simple"], "category": category,
            "crafting_time": positive(rec.get("crafting_time")),
            "ingredients": [part(v) for v in items],
            "products": [part(v) for v in products],
            **({"unlock_technologies": unlock_technologies}
               if unlock_technologies is not None else {}),
            **({"categories": categories} if categories is not None else {}),
        })
    return {
        "schema": 1, "tick": tick, "surface": surface,
        "game_version": version, "force": bounded_name(raw.get("force")),
        "research": research, "enabled_content": enabled_content,
        "truncated": raw["truncated"],
        "recipes": sorted(parsed, key=lambda x: x["name"]),
        **({"source_fingerprint": source_fingerprint} if source_fingerprint is not None else {}),
    }


def view_intelligence(frame, *, received_at=None):
    """Map an already validated dashboard frame into R04/R05 read-only state."""
    if not isinstance(frame, dict) or frame.get("status") != "ok":
        return {"status": "unavailable", "planner_ready": False,
                "reason": "No current game observation"}
    surface = bounded_name(frame.get("surface"))
    tick = frame.get("tick")
    if type(tick) is not int or tick < 0:
        raise ValueError("Invalid observed tick")
    p = frame.get("position")
    if (not isinstance(p, dict) or any(type(p.get(k)) not in (int, float)
            or not math.isfinite(p[k]) for k in ("x", "y"))):
        raise ValueError("Invalid position")
    if (type(frame.get("inventory_available")) is not bool
            or type(frame.get("truncated")) is not bool
            or not isinstance(frame.get("inventory"), list)
            or len(frame["inventory"]) > 64):
        raise ValueError("Invalid inventory state")
    if received_at is None:
        received_at = time.monotonic()
    if type(received_at) not in (int, float) or not math.isfinite(received_at) or received_at < 0:
        raise ValueError("Invalid observation clock")

    raw_caps = frame.get("capabilities")
    caps = validate_capabilities(raw_caps, surface, tick) if raw_caps is not None else None
    catalog_status = frame.get("catalog_status")
    if catalog_status is not None and not isinstance(catalog_status, dict):
        raise ValueError("Invalid recipe catalog assembly status")
    profile = caps["game_version"] if caps else "unverified-profile"
    evidence = [create_mechanic_entry(
        "character-reach", profile, mode="AI Helper",
        observed={"position": dict(p), "tick": tick, "surface": surface},
    )]
    if frame["inventory_available"]:
        evidence.append(create_mechanic_entry(
            "inventories-equipment-ammo", profile, mode="AI Helper",
            observed={"items": list(frame["inventory"]), "tick": tick,
                      "partial": frame["truncated"]},
        ))
    if caps is not None:
        evidence.append(create_mechanic_entry(
            "manufacturing-research", profile, mode="AI Helper",
            observed={"research_count": len(caps["research"]),
                      "recipe_count": len(caps["recipes"]), "tick": tick,
                      "partial": caps["truncated"]},
        ))
    ledger = create_mechanics_ledger(profile, mechanics=evidence)
    summary = compute_ledger_summary(ledger)

    if caps is None:
        return {"status": "observed", "planner_ready": False,
                "reason": "Version/research/recipe catalog unavailable or incomplete",
                "mechanics": summary, "fingerprint": None, "capabilities": None,
                "catalog_status": catalog_status}
    checked = assess_capability_snapshot({
        "schema": 1, "observed_at": received_at,
        "game_version": caps["game_version"], "force": caps["force"],
        "surface": surface, "research": caps["research"],
    }, now=received_at)
    # R04 fingerprint must change with enabled content and recipes too.
    signature_data = {key: value for key, value in caps.items() if key not in ("tick", "truncated")}
    signature = hashlib.sha256(
        json.dumps(signature_data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    total_pages = catalog_status.get("total_pages") if catalog_status is not None else None
    catalog_complete = (
        catalog_status is None
        or catalog_status.get("status") == "assembled"
        or (catalog_status.get("status") == "ok"
            and catalog_status.get("page") == 1
            and isinstance(total_pages, int) and total_pages <= 1
            and catalog_status.get("total_count") == len(caps["recipes"]))
    )
    ready = (checked["usable"] and profile_qualified(caps)
             and catalog_complete and not caps["truncated"] and bool(caps["recipes"]))
    if not profile_qualified(caps):
        reason = "Profile/expansion/mod version not independently qualified"
    elif not catalog_complete:
        reason = "Recipe catalog pages are not fully assembled"
    elif not ready:
        reason = "Recipe catalog empty/truncated: planning disabled"
    else:
        reason = "Read-only recipe catalog ready for qualified preview"
    return {"status": checked["status"], "planner_ready": ready,
            "reason": reason,
            "mechanics": summary, "fingerprint": signature, "capabilities": caps,
            "catalog_status": catalog_status}


def preview_simple_recipe(capabilities, name, *, machine_speed, machine_power_kw,
                          input_rates, power_kw, target_rate):
    """Offline one-machine item estimate ONLY; values must be supplied and observed.

    Rate arguments are per-second and are not on-hand inventory quantities.
    Caller must bind machine to real surface/force/research and validate source.
    """
    if (not isinstance(capabilities, dict) or not profile_qualified(capabilities)
            or capabilities.get("truncated") is not False
            or not capabilities.get("recipes")):
        raise ValueError("Qualified complete read-only catalog required")
    match = next((r for r in capabilities["recipes"] if r["name"] == bounded_name(name)), None)
    if match is None or not match["enabled"] or match["hidden"] or not match["simple"]:
        raise ValueError("Recipe unavailable or unverified")
    all_parts = match["ingredients"] + match["products"]
    if len(match["products"]) != 1 or any(p["type"] != "item" for p in all_parts):
        raise ValueError("Fluid or multi-output recipe needs a separate proven solver")
    if not isinstance(input_rates, dict):
        raise ValueError("Verified input-rate mapping required")
    crafting_speed = positive(machine_speed)
    power_draw = positive(machine_power_kw)
    demand = positive(target_rate)
    product = match["products"][0]
    output_rate = crafting_speed * product["amount"] / match["crafting_time"]
    inputs: list[dict[str, Any] | MaterialInput] = [{"prototype_id": item["name"],
               "count": item["amount"] / product["amount"]}
              for item in match["ingredients"]]
    planner = ProductionSolver(profile_version=capabilities["game_version"])
    planner.add_recipe(create_recipe(
        product["name"], output_rate, power_draw / output_rate,
        inputs=inputs, surface_eligible=[capabilities["surface"]],
    ))
    planner.add_machine(create_machine(product["name"], "Validated fixture machine"))
    return planner.compute_production_plan(
        product["name"], demand, input_rates, power_kw,
        surface=capabilities["surface"],
    )


class ReadOnlyPlanningSession:
    """Bounded freshness gate across successive read-only display frames."""

    def __init__(self, max_still_seconds: float = 5):
        self.max_still_seconds = positive(max_still_seconds)
        self._surface = None
        self._tick = None
        self._progressed_at = None

    def observe(self, frame, *, now=None):
        if now is None:
            now = time.monotonic()
        if type(now) not in (float, int) or not math.isfinite(now) or now < 0:
            raise ValueError("Invalid clock")
        if not isinstance(frame, dict) or frame.get("status") != "ok":
            self._surface = self._tick = self._progressed_at = None
            return view_intelligence({"status": "unavailable"})
        surface, tick = bounded_name(frame.get("surface")), frame.get("tick")
        if type(tick) is not int or tick < 0:
            raise ValueError("Invalid tick")
        if self._surface == surface and self._tick is not None and tick < self._tick:
            raise ValueError("Game observation tick regressed")
        if self._surface != surface or tick != self._tick:
            self._surface, self._tick = surface, tick
            self._progressed_at = now
        progressed_at = self._progressed_at
        if progressed_at is None:
            raise ValueError("Missing observation progress timestamp")
        if now < progressed_at:
            raise ValueError("Observation clock regressed")
        result = view_intelligence(frame, received_at=now)
        if now - progressed_at > self.max_still_seconds:
            result = dict(result, status="stale", planner_ready=False,
                          reason="Game tick stopped advancing; planning disabled")
        return result
