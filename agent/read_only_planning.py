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
from effective_yield import yield_of_part
from mechanics_coverage import (
    compute_ledger_summary,
    create_mechanic_entry,
    create_mechanics_ledger,
)
from observed_supply import observed_supply, supply_evidence
from production_solver import MaterialInput, ProductionSolver, create_machine, create_recipe

# The sole supported development and testing game version. Qualification here
# enables read-only catalog preview only; it is not evidence that a
# runtime/backend combination passed live acceptance. Any other patch version
# requires a deliberate compatibility review before it may be qualified.
QUALIFIED_GAME_VERSIONS = frozenset({"2.1.23"})
# The backend accepts catalog pages 1..10000 at 1..32 entries per page, so
# the addressable recipe catalog is bounded by the page count. A large
# modpack must page rather than be rejected by a flat entry cap.
MAX_RECIPE_CATALOG_ROWS = 10000 * 16
# The backend reports the recipes it could not represent with the reason that
# was observed. One page carries at most 32 recipe rows, so one page can
# report at most 32 exclusions; the bound is generous enough for the whole
# catalog while still refusing an unbounded payload.
MAX_EXCLUSION_ROWS = 10000 * 32
# The backend reports the crafting machines the game exposes. The adapter
# caps one page at 256 machines, so the bound covers the whole catalog while
# still refusing an unbounded payload.
MAX_MACHINE_ROWS = 10000 * 256
# The largest machine footprint, in tiles, the spatial planner accepts. A
# bigger footprint is refused instead of laid out, because the planner
# would have to invent a bounding box.
MAX_MACHINE_SIZE_TILES = 64
# Content that the R04-R06 offline gates accept without further evidence.
# Only the base game and the project's own read-only input helper are
# qualified today. Space Age, Quality, Recycler and Elevated Rails are
# first-party vanilla expansions, but they still require their own live
# qualification and are therefore not accepted here yet.
QUALIFIED_CONTENT = frozenset({"base", "core", "autoengineer-input"})
# First-party vanilla expansions. They are not third-party mods, but they are
# not qualified either, so the reason given to the operator differs from the
# reason given for an unknown mod.
FIRST_PARTY_CONTENT = frozenset({
    "space-age", "quality", "recycler", "elevated-rails",
})
# The read-only input helper is the project's own mod.
PROJECT_CONTENT = frozenset({"autoengineer-input"})


def profile_content_kind(caps):
    """Classify the observed content as "vanilla", "first-party" or "modded".

    The classification is derived from the observed enabled mod list. It
    never asserts that a third-party mod behaves like vanilla content; it
    only records which kind of profile was observed, so the R04-R06 tab can
    label an unqualified profile accurately instead of using one blanket
    message.
    """
    content = caps.get("enabled_content")
    if not isinstance(content, list):
        return "unknown"
    names = {name for name in content if isinstance(name, str)}
    if not names:
        return "unknown"
    known = QUALIFIED_CONTENT | FIRST_PARTY_CONTENT
    if names - known:
        return "modded"
    if names - QUALIFIED_CONTENT:
        return "first-party"
    return "vanilla"


def profile_qualified(caps):
    """Return True when this exact profile may use the read-only planner.

    Qualification is deliberately narrow. The game version must be the
    qualified target and the content must be the qualified base set. A
    profile with first-party expansions or third-party mods is NOT qualified
    here: it carries its own evidence requirements, which are tracked
    separately and are not satisfied by the base-game gates. The R04-R06
    catalog still *observes* such a profile and reports it as
    observed-but-unqualified with an accurate reason.
    """
    content = caps.get("enabled_content")
    if not isinstance(content, list):
        return False
    names = {name for name in content if isinstance(name, str)}
    if len(names) != len(content):
        return False
    return (caps.get("game_version") in QUALIFIED_GAME_VERSIONS
            and "base" in names
            and names.issubset(QUALIFIED_CONTENT))


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


def optional_positive(value):
    """Return a positive number, or None when the game did not report one.

    A value the observation does not carry is **unknown**, not invalid. The
    difference matters for the machine report: Factorio 2.1.23 exposes the
    crafting speed on the runtime prototype through the **method**
    ``get_crafting_speed(quality?)``, and a prototype that does not declare
    that method (a machine that is not a crafting machine) carries no speed
    at all. The machine is kept with an unknown speed, and the planner
    refuses to plan it rather than inventing a speed.

    A value that IS present must still be a positive finite number; an
    invalid one is refused.
    """
    if value is None:
        return None
    return positive(value)


def validate_exclusions(raw):
    """Return the observed recipe exclusions as a sorted list of entries.

    The backend reports the recipes it could not represent together with the
    reason that was actually observed. Nothing here is inferred: a recipe that
    is absent from the report is simply not known to be excluded, and an
    exclusion whose reason cannot be parsed is refused rather than guessed.

    The returned value keeps the wire shape, so validating an already
    validated payload is idempotent.
    """
    entries = raw.get("excluded")
    if entries is None or entries == {}:
        return []
    if not isinstance(entries, list) or len(entries) > MAX_EXCLUSION_ROWS:
        raise ValueError("Missing or unbounded recipe exclusion report")
    excluded: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"name", "reason"}:
            raise ValueError("Invalid recipe exclusion entry")
        name = bounded_name(entry.get("name"))
        reason = entry.get("reason")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 128:
            raise ValueError("Invalid recipe exclusion reason")
        if name in excluded:
            raise ValueError("Duplicate recipe exclusion")
        excluded[name] = reason
    return [{"name": name, "reason": excluded[name]} for name in sorted(excluded)]


def accounted_recipe_count(capabilities):
    """Count represented recipes without granting support to excluded ones."""
    recipes = capabilities.get("recipes", [])
    if not isinstance(recipes, list):
        raise ValueError("Invalid recipe coverage")
    names = [bounded_name(row.get("name")) for row in recipes if isinstance(row, dict)]
    exclusions = validate_exclusions(capabilities)
    excluded_names = {row["name"] for row in exclusions}
    if (len(names) != len(recipes) or len(set(names)) != len(names)
            or set(names) & excluded_names):
        raise ValueError("Duplicate or overlapping recipe coverage")
    return len(names) + len(excluded_names)


def classify_exclusions(excluded):
    """Group the observed exclusions by the cause the game actually showed.

    The grouping keeps the full reason string so that a cause the backend
    reports in more detail is never collapsed into a coarser one.
    """
    groups: dict[str, list[str]] = {}
    for entry in excluded:
        groups.setdefault(entry["reason"], []).append(entry["name"])
    return dict(sorted(groups.items()))


#: The module and beacon effect names that Factorio 2.1.23 declares in its
#: ``EffectTypeLimitation`` union. The union is exactly these five literals,
#: so an effect outside this set is not a 2.1.23 effect and is refused
#: rather than accepted on trust.
ALLOWED_EFFECT_NAMES = frozenset({
    "speed", "productivity", "consumption", "pollution", "quality",
})

#: The fluid-box production types that Factorio 2.1.23 declares in its
#: ``ProductionType`` literal union.
FLUID_BOX_PRODUCTION_TYPES = frozenset({
    "none", "input", "output", "input-output",
})


def parse_fluid_box(box):
    """Return the observed fluid box of one crafting machine.

    Factorio 2.1.23 ``FluidBox`` declares ``production_type`` (a
    ``ProductionType`` literal), ``filter`` (a FluidID) and ``volume``. It
    does **not** declare ``filter_type`` or ``fluid_box_index``; the earlier
    adapter read those names, so the reported filter was always the literal
    fallback "item" and the index was always absent. Only the declared
    fields are read here, and an unknown field still fails closed.
    """
    if not isinstance(box, dict):
        raise ValueError("Invalid machine fluid box")
    unknown = set(box) - {"production_type", "filter", "volume"}
    if unknown:
        raise ValueError("Unsupported machine fluid box fields")
    parsed: dict[str, Any] = {}
    if "production_type" in box:
        production_type = box["production_type"]
        if (not isinstance(production_type, str)
                or production_type not in FLUID_BOX_PRODUCTION_TYPES):
            raise ValueError("Invalid machine fluid box production type")
        parsed["production_type"] = production_type
    if "filter" in box:
        parsed["filter"] = bounded_name(box["filter"])
    if "volume" in box:
        parsed["volume"] = positive(box["volume"])
    return parsed


def parse_machine_size(value):
    """Return the observed tile footprint of one machine prototype.

    Factorio 2.1.23 declares the entity size as a width/height pair in
    whole tiles. The planner needs it to place machines without
    overlapping them, so both dimensions have to be positive whole
    numbers. A size that the game did not report, or that is unusable, is
    refused here instead of being given a default: a guessed footprint
    would silently overlap a neighbour.
    """
    if not isinstance(value, dict):
        raise ValueError("Invalid machine size")
    unknown = set(value) - {"width", "height"}
    if unknown:
        raise ValueError("Unsupported machine size fields")
    size = {}
    for key in ("width", "height"):
        dimension = value.get(key)
        if type(dimension) is not int or dimension <= 0:
            raise ValueError("Invalid machine size")
        size[key] = dimension
    if size["width"] * size["height"] > MAX_MACHINE_SIZE_TILES:
        raise ValueError("Machine size exceeds the supported footprint")
    return size


def parse_machine_directions(value):
    """Return the observed orientations one machine prototype supports.

    The list is kept as the observed directions, sorted and free of
    duplicates. It is a *support* list, not a placement: the planner still
    chooses the orientation and records it in the blueprint.
    """
    if not isinstance(value, list) or not value or len(value) > 8:
        raise ValueError("Invalid machine directions")
    directions = []
    for direction in value:
        if type(direction) is not int or not 0 <= direction <= 7:
            raise ValueError("Invalid machine direction")
        directions.append(direction)
    if len(set(directions)) != len(directions):
        raise ValueError("Duplicate machine direction")
    return sorted(directions)


def parse_quality_multipliers(value):
    """Return the observed per-quality crafting speed multipliers.

    Factorio 2.1.23 declares ``crafting_speed_quality_multiplier`` as a
    dictionary of ``QualityID`` to a double, and it is declared only on the
    ``CraftingMachine`` subclass, so a machine without the attribute has no
    multipliers at all. A multiplier that is present must be a finite
    non-negative number; an invalid one is refused rather than dropped,
    because a wrong multiplier would silently change every rate.
    """
    if not isinstance(value, dict) or len(value) > 32:
        raise ValueError("Invalid machine crafting speed quality multipliers")
    parsed: dict[str, float] = {}
    for quality, factor in value.items():
        if not isinstance(quality, str) or not 1 <= len(quality) <= 128:
            raise ValueError("Invalid machine crafting speed quality name")
        if type(factor) not in (int, float) or not math.isfinite(factor) \
                or factor < 0:
            raise ValueError("Invalid machine crafting speed quality multiplier")
        parsed[quality] = float(factor)
    return parsed


def parse_allowed_effects(value):
    """Return the module and beacon effects a machine permits.

    Factorio 2.1.23 declares ``allowed_effects`` as an
    ``EffectTypeLimitation``: either a single effect literal or an array of
    them. The API states that an empty array means the machine cannot be
    affected by modules or beacons at all, so an empty list is a real
    observed rule and is preserved rather than treated as missing.
    """
    if isinstance(value, dict) and not value:
        value = []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("Invalid machine allowed effects")
    if len(values) > len(ALLOWED_EFFECT_NAMES):
        raise ValueError("Invalid machine allowed effects")
    effects = []
    for effect in values:
        if not isinstance(effect, str) or effect not in ALLOWED_EFFECT_NAMES:
            raise ValueError("Invalid machine allowed effect")
        if effect not in effects:
            effects.append(effect)
    return sorted(effects)


def parse_module_categories(value):
    """Return the module categories a machine permits.

    Factorio 2.1.23 declares ``allowed_module_categories`` as an array of
    ``ModuleCategoryID``. A mod may add its own category, so the observed
    name is kept verbatim and is never checked against the vanilla set.
    """
    if isinstance(value, dict) and not value:
        value = []
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("Invalid machine allowed module categories")
    categories = [bounded_name(category) for category in value]
    if len(set(categories)) != len(categories):
        raise ValueError("Duplicate machine allowed module category")
    return sorted(categories)


def validate_machines(raw):
    """Return the observed crafting machines keyed by prototype name.

    A machine is only reported when the game itself declares the fields the
    planner needs: the crafting categories it can run, its crafting speed
    and its energy usage. A machine whose speed or energy the game does not
    expose is refused here rather than given a default, so an unknown
    machine property stays unknown.
    """
    entries = raw.get("machines")
    if entries is None:
        return []
    if not isinstance(entries, list) or len(entries) > MAX_MACHINE_ROWS:
        raise ValueError("Missing or unbounded machine report")
    machines: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid machine entry")
        unknown = set(entry) - {
            "name", "crafting_categories", "crafting_speed", "energy_usage", "energy_drain",
            "module_slots", "fluid_boxes", "allowed_effects",
            "allowed_module_categories", "quality_affects_module_slots",
            "crafting_speed_quality_multiplier",
            "size", "directions",
        }
        if unknown:
            raise ValueError("Unsupported machine fields")
        name = bounded_name(entry.get("name"))
        if name in seen:
            raise ValueError("Duplicate machine")
        seen.add(name)
        categories = entry.get("crafting_categories")
        if (not isinstance(categories, list) or not categories
                or len(categories) > 32):
            raise ValueError("Invalid machine crafting categories")
        parsed_categories = [bounded_name(category) for category in categories]
        if len(set(parsed_categories)) != len(parsed_categories):
            raise ValueError("Duplicate machine crafting category")
        machine: dict[str, Any] = {
            "name": name,
            "crafting_categories": parsed_categories,
            # Factorio 2.1.23 exposes the crafting speed on the runtime
            # prototype through the METHOD get_crafting_speed(quality?).
            # A prototype that does not declare that method carries no
            # speed at all. An unknown speed is kept as None rather than
            # refused, so the machine stays visible to the planner, which
            # then refuses to plan it and never invents a speed. A speed
            # that IS present must still be a positive number.
            "crafting_speed": optional_positive(entry.get("crafting_speed")),
            "energy_usage": optional_positive(entry.get("energy_usage")),
        }
        if "energy_drain" in entry:
            drain = entry["energy_drain"]
            if type(drain) not in (int, float) or not math.isfinite(drain) or drain < 0:
                raise ValueError("Invalid machine idle drain")
            machine["energy_drain"] = float(drain)
        if "module_slots" in entry:
            slots = entry["module_slots"]
            if type(slots) is not int or slots < 0:
                raise ValueError("Invalid machine module slots")
            machine["module_slots"] = slots
        if "quality_affects_module_slots" in entry:
            affects = entry["quality_affects_module_slots"]
            if type(affects) is not bool:
                raise ValueError("Invalid machine quality module slot flag")
            machine["quality_affects_module_slots"] = affects
        if "crafting_speed_quality_multiplier" in entry:
            machine["crafting_speed_quality_multiplier"] = (
                parse_quality_multipliers(
                    entry["crafting_speed_quality_multiplier"]))
        if "fluid_boxes" in entry:
            boxes = entry["fluid_boxes"]
            if isinstance(boxes, dict) and not boxes:
                boxes = []
            if not isinstance(boxes, list) or len(boxes) > 16:
                raise ValueError("Invalid machine fluid boxes")
            machine["fluid_boxes"] = [
                parse_fluid_box(box) for box in boxes
            ]
        if "size" in entry:
            machine["size"] = parse_machine_size(entry["size"])
        if "directions" in entry:
            machine["directions"] = parse_machine_directions(entry["directions"])
        if "allowed_effects" in entry:
            machine["allowed_effects"] = parse_allowed_effects(
                entry["allowed_effects"])
        if "allowed_module_categories" in entry:
            machine["allowed_module_categories"] = parse_module_categories(
                entry["allowed_module_categories"])
        machines.append(machine)
    return sorted(machines, key=lambda machine: machine["name"])


def machine_options(recipes, machines, category):
    """Return the observed machines that can run the given crafting category.

    The result is a list of machine descriptions, each with its observed
    crafting speed and energy usage. A recipe category that no observed
    machine declares has no machine, and the caller must say that the
    target is unresolved instead of assuming a default machine.

    A machine whose crafting speed or energy the game did not report is
    **not** an option: the rate of a machine without an observed speed
    cannot be computed, so it is left out rather than planned with an
    invented number.
    """
    wanted = bounded_name(category)
    return [
        {
            "name": machine["name"],
            "crafting_speed": machine["crafting_speed"],
            "energy_usage": machine["energy_usage"],
            **({"energy_drain": machine["energy_drain"]} if "energy_drain" in machine else {}),
            **({"module_slots": machine["module_slots"]}
               if "module_slots" in machine else {}),
            **({"quality_affects_module_slots":
                machine["quality_affects_module_slots"]}
               if "quality_affects_module_slots" in machine else {}),
            **({"crafting_speed_quality_multiplier":
                machine["crafting_speed_quality_multiplier"]}
               if "crafting_speed_quality_multiplier" in machine else {}),
            **({"size": machine["size"]} if "size" in machine else {}),
            **({"directions": machine["directions"]}
               if "directions" in machine else {}),
        }
        for machine in machines
        if wanted in machine["crafting_categories"]
        and machine["crafting_speed"] is not None
        and machine["energy_usage"] is not None
    ]


def machine_energy_kw(machine):
    """Return the machine's working power draw in kilowatts.

    The observer normalizes runtime joules/tick to watts (multiply by 60)
    before publishing ``energy_usage``. This adapter divides that normalized
    value by 1000; it must not apply the runtime conversion a second time.
    """
    return machine["energy_usage"] / 1000.0


def plan_recipe_production(capabilities, name, *, target_per_second,
                            module_speed_bonus=0.0, beacon_speed_bonus=0.0,
                            productivity_bonus=0.0):
    """Plan one recipe against the observed machines of the observed catalog.

    The result states, for every observed machine that can run the recipe's
    crafting category, the items per second and per minute it produces, the
    number of machines needed for the target, the ingredient consumption per
    second and per minute, and the electricity demand in kilowatts.

    Every number is derived from the observed recipe row and the observed
    machine row. When the catalog carries no machine for the recipe's
    category, or when the recipe has more than one product, the result is
    explicitly unresolved rather than estimated.
    """
    if (not isinstance(capabilities, dict)
            or not capabilities.get("recipes")
            or not isinstance(capabilities.get("machines"), list)):
        raise ValueError("Observed catalog with machines required")
    recipe_name = bounded_name(name)
    target = positive(target_per_second)
    match = next((r for r in capabilities["recipes"]
                  if r["name"] == recipe_name), None)
    if match is None:
        raise ValueError("Recipe is not in the observed catalog")
    if not match["enabled"]:
        raise ValueError("Recipe is disabled in the observed game data")
    if len(match["products"]) != 1:
        raise ValueError("Multi-output recipe needs a separate proven solver")
    product = match["products"][0]
    if product.get("deterministic") is False:
        raise ValueError("Stochastic yield needs a separate proven solver")
    if type(product["amount"]) is not int and type(product["amount"]) is not float:
        raise ValueError("Invalid product amount")
    yield_per_craft = float(product["amount"])
    crafting_time = positive(match["crafting_time"])
    options = machine_options(capabilities["recipes"], capabilities["machines"],
                              match["category"])
    if not options:
        return {
            "status": "unresolved",
            "reason": "No observed machine can run this crafting category",
            "recipe": recipe_name,
            "category": match["category"],
            "target_per_second": target,
        }
    module_bonus = positive_or_zero(module_speed_bonus)
    beacon_bonus = positive_or_zero(beacon_speed_bonus)
    productivity = positive_or_zero(productivity_bonus)
    machines = []
    for option in options:
        effective_speed = option["crafting_speed"] * (1.0 + module_bonus) * (1.0 + beacon_bonus)
        crafts_per_second = effective_speed / crafting_time
        items_per_second = crafts_per_second * yield_per_craft * (1.0 + productivity)
        needed = math.ceil(target / items_per_second) if items_per_second > 0 else 0
        ingredients = {
            f"{part['type']}:{part['name']}": part["amount"] * crafts_per_second
            for part in match["ingredients"]
        }
        energy_kw = machine_energy_kw(option) * needed
        machines.append({
            "machine": option["name"],
            "effective_speed": effective_speed,
            "crafts_per_second": crafts_per_second,
            "items_per_second": items_per_second,
            "items_per_minute": items_per_second * 60.0,
            "machines_needed": needed,
            "ingredients_per_second": ingredients,
            "ingredients_per_minute": {key: value * 60.0
                                       for key, value in ingredients.items()},
            "energy_kw": energy_kw,
        })
    return {
        "status": "ok",
        "recipe": recipe_name,
        "category": match["category"],
        "target_per_second": target,
        "target_per_minute": target * 60.0,
        "machines": sorted(machines, key=lambda row: row["machine"]),
    }


def productivity_multiplier(productivity_bonus, product):
    """Return the productivity factor that applies to one product.

    Factorio 2.1.23 declares ``ignored_by_productivity`` as the amount
    deducted from a productivity-induced bonus craft. A product that
    ignores the whole bonus is not scaled by it, so the bonus is applied
    only to the part of the output that the game says responds to it.

    The deduction is applied as a whole-unit reduction on the bonus craft,
    which is what the uint16 amount means: a product with
    ``ignored_by_productivity = 1`` loses one unit of every bonus craft.
    """
    bonus = positive_or_zero(productivity_bonus)
    ignored = product.get("ignored_by_productivity")
    if bonus <= 0:
        return 1.0
    if ignored is None:
        return 1.0 + bonus
    ignored_units = float(ignored)
    if ignored_units <= 0:
        return 1.0 + bonus
    # The bonus craft adds ``amount`` units; the deduction removes
    # ``ignored_by_productivity`` of them. The factor is therefore the
    # bonus amount that survives, divided by the base amount.
    amount = float(product["amount"])
    if amount <= 0:
        return 1.0
    bonus_units = amount * bonus
    surviving = bonus_units - ignored_units
    if surviving < 0:
        surviving = 0.0
    return 1.0 + surviving / amount


def plan_stochastic_recipe(capabilities, name, *, target_per_second,
                           module_speed_bonus=0.0, beacon_speed_bonus=0.0,
                           productivity_bonus=0.0):
    """Plan one recipe whose output may be probabilistic or ranged.

    The result separates three different quantities that are often
    confused:

    * ``guaranteed_per_second`` - the output that happens on **every**
      craft. It is only reported when the observed mechanics make the
      amount certain.
    * ``expected_per_second`` - the long-run average. It is only reported
      when the observed probability justifies it: Factorio 2.1.23 declares
      ``independent_probability`` as a per-craft probability and
      ``extra_count_fraction`` as the probability of one extra unit, so
      ``probability * amount`` is a real expectation. A product whose
      amount is a **range** has no verified distribution inside the range,
      so its expectation stays unknown rather than being guessed as the
      midpoint.
    * ``minimum_per_second`` / ``maximum_per_second`` - the bounds.

    Every byproduct is reported with the same three quantities, so a caller
    can tell a guaranteed byproduct from an occasional one. A recipe that
    the observed data cannot plan is reported as unresolved with a reason;
    no deterministic promise is ever made from a random yield.
    """
    if (not isinstance(capabilities, dict)
            or not capabilities.get("recipes")
            or not isinstance(capabilities.get("machines"), list)):
        raise ValueError("Observed catalog with machines required")
    recipe_name = bounded_name(name)
    target = positive(target_per_second)
    match = next((r for r in capabilities["recipes"]
                  if r["name"] == recipe_name), None)
    if match is None:
        raise ValueError("Recipe is not in the observed catalog")
    if not match["enabled"]:
        raise ValueError("Recipe is disabled in the observed game data")
    crafting_time = positive(match["crafting_time"])
    options = machine_options(capabilities["recipes"], capabilities["machines"],
                              match["category"])
    if not options:
        return {
            "status": "unresolved",
            "reason": "No observed machine can run this crafting category",
            "recipe": recipe_name,
            "category": match["category"],
            "target_per_second": target,
        }
    module_bonus = positive_or_zero(module_speed_bonus)
    beacon_bonus = positive_or_zero(beacon_speed_bonus)
    productivity = positive_or_zero(productivity_bonus)

    # Every product of the recipe is read, so a multi-output recipe reports
    # its main product and its byproducts separately instead of refusing.
    primary = None
    outputs: list[dict[str, Any]] = []
    for product in match["products"]:
        amount = product["amount"]
        if type(amount) not in (int, float) or amount <= 0:
            raise ValueError("Invalid product amount")
        yld = yield_of_part(product)
        factor = productivity_multiplier(productivity, product)
        guaranteed = None
        if yld.guaranteed is not None:
            guaranteed = yld.guaranteed * factor
        expected = None
        if yld.expected is not None:
            expected = yld.expected * factor
        # The bounds are always numbers: the yield model sets them for
        # every part, and a missing bound would otherwise be multiplied.
        minimum = yld.minimum if yld.minimum is not None else float(amount)
        maximum = yld.maximum if yld.maximum is not None else float(amount)
        entry: dict[str, Any] = {
            "name": product["name"],
            "type": product["type"],
            "amount": float(amount),
            "guaranteed_per_craft": guaranteed,
            "expected_per_craft": expected,
            "minimum_per_craft": minimum * factor,
            "maximum_per_craft": maximum * factor,
            "deterministic": yld.deterministic,
            "reasons": list(yld.reasons),
        }
        outputs.append(entry)
        if primary is None and product["type"] == "item":
            primary = entry
    if primary is None:
        return {
            "status": "unresolved",
            "reason": "The recipe has no item product to plan against",
            "recipe": recipe_name,
            "category": match["category"],
            "target_per_second": target,
        }

    machines = []
    for option in options:
        effective_speed = option["crafting_speed"] * (1.0 + module_bonus) * (1.0 + beacon_bonus)
        crafts_per_second = effective_speed / crafting_time
        rows = []
        for entry in outputs:
            row = dict(entry)
            row["guaranteed_per_second"] = (
                None if entry["guaranteed_per_craft"] is None
                else entry["guaranteed_per_craft"] * crafts_per_second)
            row["expected_per_second"] = (
                None if entry["expected_per_craft"] is None
                else entry["expected_per_craft"] * crafts_per_second)
            row["minimum_per_second"] = entry["minimum_per_craft"] * crafts_per_second
            row["maximum_per_second"] = entry["maximum_per_craft"] * crafts_per_second
            row["is_byproduct"] = entry is not primary
            rows.append(row)
        main = next(row for row in rows if not row["is_byproduct"])
        guaranteed_rate = main["guaranteed_per_second"]
        expected_rate = main["expected_per_second"]
        needed = None
        if guaranteed_rate:
            needed = math.ceil(target / guaranteed_rate)
        elif expected_rate:
            # A probabilistic output has no guaranteed rate, so the machine
            # count is the expected count, and the plan says so.
            needed = math.ceil(target / expected_rate)
        ingredients = {
            f"{part['type']}:{part['name']}": part["amount"] * crafts_per_second
            for part in match["ingredients"]
        }
        machines.append({
            "machine": option["name"],
            "effective_speed": effective_speed,
            "crafts_per_second": crafts_per_second,
            "machines_needed": needed,
            "machines_needed_basis": (
                "guaranteed" if guaranteed_rate else
                "expected" if expected_rate else "unresolved"),
            "guaranteed_per_second": guaranteed_rate,
            "expected_per_second": expected_rate,
            "minimum_per_second": main["minimum_per_second"],
            "maximum_per_second": main["maximum_per_second"],
            "products": rows,
            "byproducts": [row for row in rows if row["is_byproduct"]],
            "ingredients_per_second": ingredients,
            "ingredients_per_minute": {key: value * 60.0
                                       for key, value in ingredients.items()},
            "energy_kw": machine_energy_kw(option) * (needed or 0),
        })
    return {
        "status": "ok",
        "recipe": recipe_name,
        "category": match["category"],
        "target_per_second": target,
        "target_per_minute": target * 60.0,
        "machines": sorted(machines, key=lambda row: row["machine"]),
    }


def plan_blueprint(capabilities, name, *, target_per_second,
                   module_speed_bonus=0.0, beacon_speed_bonus=0.0,
                   productivity_bonus=0.0):
    """Plan a read-only blueprint layout for one recipe.

    The plan answers the questions a blueprint needs answered, using only
    the observed catalog and the observed machines:

    * **which machines** can craft the recipe, and for each one the
      crafting speed, the module slots, the allowed effects and the fluid
      boxes the game declares for it;
    * **how many machines** are required for the wanted rate;
    * the **input and output throughput** per second and per minute, with
      the guaranteed output kept apart from the expected output;
    * the **power requirement** in kilowatts;
    * the **byproducts** and their throughput, so they can be routed
      instead of blocking a belt;
    * the **technologies** that unlock the recipe, with the researched flag
      the game reports;
    * the **alternative machine configurations**, one per observed machine
      that can run the recipe's category.

    Nothing here places a blueprint or writes to the game. The result is a
    planning model: a recipe that the observed data cannot plan is
    reported as unresolved, and a probabilistic output is never presented
    as a guaranteed one.
    """
    if (not isinstance(capabilities, dict)
            or not capabilities.get("recipes")
            or not isinstance(capabilities.get("machines"), list)):
        raise ValueError("Observed catalog with machines required")
    recipe_name = bounded_name(name)
    target = positive(target_per_second)
    match = next((r for r in capabilities["recipes"]
                  if r["name"] == recipe_name), None)
    if match is None:
        raise ValueError("Recipe is not in the observed catalog")
    if not match["enabled"]:
        raise ValueError("Recipe is disabled in the observed game data")

    technologies = []
    for unlock in match.get("unlock_technologies") or []:
        technologies.append({
            "name": unlock["name"],
            "researched": unlock["researched"],
            "enabled": unlock["enabled"],
        })

    production = plan_stochastic_recipe(
        capabilities, recipe_name, target_per_second=target,
        module_speed_bonus=module_speed_bonus,
        beacon_speed_bonus=beacon_speed_bonus,
        productivity_bonus=productivity_bonus,
    )
    if production["status"] != "ok":
        return {
            "status": "unresolved",
            "reason": production["reason"],
            "recipe": recipe_name,
            "category": production.get("category"),
            "technologies": technologies,
            "target_per_second": target,
        }

    machines = []
    for option in production["machines"]:
        observed = next(m for m in capabilities["machines"]
                        if m["name"] == option["machine"])
        machines.append({
            "machine": option["machine"],
            "crafting_speed": observed["crafting_speed"],
            "effective_speed": option["effective_speed"],
            "machines_needed": option["machines_needed"],
            "machines_needed_basis": option["machines_needed_basis"],
            "module_slots": observed.get("module_slots"),
            "allowed_effects": observed.get("allowed_effects"),
            "allowed_module_categories": observed.get("allowed_module_categories"),
            "fluid_boxes": observed.get("fluid_boxes"),
            "crafts_per_second": option["crafts_per_second"],
            "guaranteed_per_second": option["guaranteed_per_second"],
            "expected_per_second": option["expected_per_second"],
            "minimum_per_second": option["minimum_per_second"],
            "maximum_per_second": option["maximum_per_second"],
            "products": option["products"],
            "byproducts": option["byproducts"],
            "ingredients_per_second": option["ingredients_per_second"],
            "ingredients_per_minute": option["ingredients_per_minute"],
            "energy_kw": option["energy_kw"],
        })
    recommended = None
    if machines:
        # The cheapest machine that reaches the target wins; when none
        # reaches it, the fastest one is reported so the shortfall is
        # visible instead of hidden.
        recommended = min(
            machines,
            key=lambda row: (row["machines_needed"] is None,
                             row["machines_needed"] or 0,
                             row["energy_kw"],
                             row["machine"]),
        )["machine"]
    return {
        "status": "ok",
        "recipe": recipe_name,
        "category": production["category"],
        "target_per_second": target,
        "target_per_minute": target * 60.0,
        "technologies": technologies,
        "machines": sorted(machines, key=lambda row: row["machine"]),
        "recommended_machine": recommended,
    }


def positive_or_zero(value):
    """Return a finite non-negative number, refusing anything else."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Expected a finite non-negative number")
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
    research = bounded_names(raw.get("research"), 16384)
    enabled_content = bounded_names(raw.get("enabled_content"), 32)
    recipes = raw.get("recipes")
    if isinstance(recipes, dict) and not recipes:
        recipes = []
    # A large modpack carries far more recipes than the base game. The bound
    # is the backend's own addressable catalog (10000 pages of 16 entries),
    # not a flat 10,000-entry cap, so a modded catalog is page-assembled
    # rather than rejected.
    if not isinstance(recipes, list) or len(recipes) > MAX_RECIPE_CATALOG_ROWS:
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

        def part(data, is_product=True):
            if not isinstance(data, dict):
                raise ValueError("Unsupported item/fluid attributes")
            allowed = {"name", "type", "amount"} | (
                {"deterministic"} if "deterministic" in data else set()
            )
            # Factorio 2.1.23 declares the observed fluid temperature fields on
            # FluidProductPrototype and FluidIngredientPrototype, the observed
            # quality fields on ItemProductPrototype and
            # ItemIngredientPrototype, and the observed quantity fields on the
            # product prototypes. Each group is accepted only on its own
            # material type, with a bounded value, and every other unknown
            # field still fails closed.
            fluid_fields = ("temperature", "minimum_temperature", "maximum_temperature")
            item_fields = ("quality_min", "quality_max", "quality_change")
            product_fields = ("amount_min", "amount_max", "extra_count_fraction")
            productivity_fields = ("ignored_by_productivity", "always_fresh",
                                    "reset_freshness_on_craft", "percent_spoiled")
            display_fields = ("optional_fluidbox_indexes",
                              "show_details_in_recipe_tooltip")
            # ignored_by_stats is declared on both products and ingredients.
            stats_fields = ("ignored_by_stats",)
            # The backend already reports the observed probability fields and
            # the quality-affect flag, so the validator must accept them
            # instead of dropping the recipes that carry them.
            probability_fields = ("independent_probability", "shared_probability")
            quality_flag_fields = ("affected_by_quality",)
            for key in (fluid_fields + item_fields + product_fields
                        + productivity_fields + display_fields + stats_fields
                        + probability_fields + quality_flag_fields):
                if key in data:
                    allowed.add(key)
            if (set(data) != allowed or data.get("type") not in ("item", "fluid")):
                raise ValueError("Unsupported item/fluid attributes")
            part_type = data["type"]
            parsed_part = {"name": bounded_name(data.get("name")),
                           "type": part_type, "amount": positive(data.get("amount"))}
            if "deterministic" in data:
                if type(data["deterministic"]) is not bool:
                    raise ValueError("Invalid product determinism marker")
                parsed_part["deterministic"] = data["deterministic"]
            for key in fluid_fields:
                if key not in data:
                    continue
                if part_type != "fluid":
                    raise ValueError("Unsupported item/fluid attributes")
                value = data[key]
                if type(value) not in (int, float) or type(value) is bool:
                    raise ValueError("Unsupported item/fluid attributes")
                if not math.isfinite(value):
                    raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = value
            for key in item_fields:
                if key not in data:
                    continue
                if part_type != "item":
                    raise ValueError("Unsupported item/fluid attributes")
                value = data[key]
                if key == "quality_change":
                    if type(value) is not int:
                        raise ValueError("Unsupported item/fluid attributes")
                else:
                    # A QualityID is any QualityPrototype name, so a mod may
                    # add its own tier. The observed name is kept verbatim.
                    if not isinstance(value, str) or not 1 <= len(value) <= 128:
                        raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = value
            for key in product_fields:
                if key not in data:
                    continue
                # The quantity fields are declared by the product prototypes
                # only, so an ingredient carrying one is not a valid shape.
                if not is_product:
                    raise ValueError("Unsupported item/fluid attributes")
                value = data[key]
                if type(value) not in (int, float) or type(value) is bool:
                    raise ValueError("Unsupported item/fluid attributes")
                if not math.isfinite(value):
                    raise ValueError("Unsupported item/fluid attributes")
                if key == "extra_count_fraction":
                    # The probability that a craft yields one extra product.
                    if value < 0 or value > 1:
                        raise ValueError("Unsupported item/fluid attributes")
                else:
                    # A quantity range bound is a whole non-negative number.
                    if value < 0 or value % 1 != 0:
                        raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = value
            if "amount_min" in parsed_part and "amount_max" in parsed_part:
                if parsed_part["amount_min"] > parsed_part["amount_max"]:
                    raise ValueError("Unsupported item/fluid attributes")
            for key in productivity_fields:
                if key not in data:
                    continue
                # The productivity and freshness fields are declared by the
                # product prototypes only.
                if not is_product:
                    raise ValueError("Unsupported item/fluid attributes")
                value = data[key]
                if key in ("always_fresh", "reset_freshness_on_craft"):
                    if type(value) is not bool:
                        raise ValueError("Unsupported item/fluid attributes")
                else:
                    if type(value) not in (int, float) or type(value) is bool:
                        raise ValueError("Unsupported item/fluid attributes")
                    if not math.isfinite(value):
                        raise ValueError("Unsupported item/fluid attributes")
                    if key == "ignored_by_productivity":
                        # A uint16 amount deducted from a bonus craft.
                        if value < 0 or value % 1 != 0:
                            raise ValueError("Unsupported item/fluid attributes")
                    else:
                        # percent_spoiled must be >= 0 and < 1.
                        if value < 0 or value >= 1:
                            raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = value
            for key in display_fields:
                if key not in data:
                    continue
                value = data[key]
                if key == "show_details_in_recipe_tooltip":
                    # Declared by ProductPrototypeBase, so a product only.
                    if not is_product or type(value) is not bool:
                        raise ValueError("Unsupported item/fluid attributes")
                    parsed_part[key] = value
                    continue
                # optional_fluidbox_indexes is an array of uint32 and belongs
                # to the fluid prototypes only.
                if part_type != "fluid":
                    raise ValueError("Unsupported item/fluid attributes")
                if not isinstance(value, list) or len(value) > 16:
                    raise ValueError("Unsupported item/fluid attributes")
                indexes = []
                for index in value:
                    if type(index) is not int or index < 0:
                        raise ValueError("Unsupported item/fluid attributes")
                    indexes.append(index)
                if len(set(indexes)) != len(indexes):
                    raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = sorted(indexes)
            for key in stats_fields:
                if key not in data:
                    continue
                value = data[key]
                # Factorio 2.1.23 declares ignored_by_stats as a uint16 on the
                # item prototypes and as a FluidAmount on the fluid ones. It
                # is the amount excluded from the production or consumption
                # statistics, and the exact value is preserved.
                if type(value) not in (int, float) or type(value) is bool:
                    raise ValueError("Unsupported item/fluid attributes")
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Unsupported item/fluid attributes")
                if part_type == "item":
                    # A uint16 holds a whole number in 0..65535.
                    if value % 1 != 0 or value > 65535:
                        raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = value
            for key in probability_fields:
                if key not in data:
                    continue
                # The probability fields are declared by the product
                # prototypes only.
                if not is_product:
                    raise ValueError("Unsupported item/fluid attributes")
                value = data[key]
                if key == "independent_probability":
                    if (type(value) not in (int, float) or type(value) is bool
                            or not math.isfinite(value)
                            or value < 0 or value > 1):
                        raise ValueError("Unsupported item/fluid attributes")
                    parsed_part[key] = value
                    continue
                # shared_probability is a {min,max} definition.
                if not isinstance(value, dict) or set(value) != {"min", "max"}:
                    raise ValueError("Unsupported item/fluid attributes")
                low, high = value["min"], value["max"]
                for bound in (low, high):
                    if (type(bound) not in (int, float) or type(bound) is bool
                            or not math.isfinite(bound)
                            or bound < 0 or bound > 1):
                        raise ValueError("Unsupported item/fluid attributes")
                if low > high:
                    raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = {"min": low, "max": high}
            for key in quality_flag_fields:
                if key not in data:
                    continue
                if not is_product or type(data[key]) is not bool:
                    raise ValueError("Unsupported item/fluid attributes")
                parsed_part[key] = data[key]
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
            # The backend reports a recipe's unlock technologies as a list.
            # A recipe with **no** unlock technology is reported by the Lua
            # adapter as an empty table, which serialises as an empty JSON
            # object rather than an empty array. Both shapes mean the same
            # thing - the recipe has no unlock effect - so the empty object
            # is accepted and read as an empty list. A live Pyanodons run
            # proved this: 3,444 of the 9,467 observed recipes carried the
            # empty object, and rejecting them lost the whole catalog
            # frame.
            if isinstance(raw_unlocks, dict):
                if raw_unlocks:
                    raise ValueError("Invalid recipe technology unlock list")
                raw_unlocks = []
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
            "ingredients": [part(v, False) for v in items],
            "products": [part(v, True) for v in products],
            **({"unlock_technologies": unlock_technologies}
               if unlock_technologies is not None else {}),
            **({"categories": categories} if categories is not None else {}),
        })
    excluded = validate_exclusions(raw)
    machines = validate_machines(raw)
    accounted_recipe_count({"recipes": parsed, "excluded": excluded})
    return {
        "schema": 1, "tick": tick, "surface": surface,
        "game_version": version, "force": bounded_name(raw.get("force")),
        "research": research, "enabled_content": enabled_content,
        "truncated": raw["truncated"],
        "recipes": sorted(parsed, key=lambda x: x["name"]),
        "excluded": excluded,
        "machines": machines,
        **({"source_fingerprint": source_fingerprint} if source_fingerprint is not None else {}),
    }


def view_intelligence(frame, *, received_at=None, inventory_observation=None):
    """Map an already validated dashboard frame into R04/R05 read-only state.

    ``inventory_observation`` is the validated ``autoengineer_inventory``
    frame. When it is given, the planner also learns what the factory
    **actually holds** and which machines it **actually runs**, so it can
    tell the available supply apart from the theoretical requirement.

    The observation is optional: a planner without it still works, it
    simply knows less about the current factory.
    """
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
    # The R10-B observation tells the planner what the factory actually
    # holds and which machines it actually runs. It is attached to the
    # same mechanic the player inventory feeds, so the planner reasons
    # about the **current** factory and not only about the theoretical
    # recipe graph.
    supply = observed_supply(inventory_observation)
    if frame["inventory_available"] or supply.known:
        observed: dict[str, Any] = {
            "tick": tick,
            "partial": frame["truncated"] or supply.partial,
        }
        if frame["inventory_available"]:
            observed["items"] = list(frame["inventory"])
        if supply.known:
            observed["supply"] = supply_evidence(supply)
        evidence.append(create_mechanic_entry(
            "inventories-equipment-ammo", profile, mode="AI Helper",
            observed=observed,
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
                "catalog_status": catalog_status,
                # The observed supply is reported even when the recipe
                # catalog is not available: what the factory holds is
                # known independently of the theoretical recipe graph.
                "observed_supply": supply.as_dict() if supply.known else None,
                "supply_observed": supply.known}
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
            and catalog_status.get("total_count") == accounted_recipe_count(caps))
    )
    ready = (checked["usable"] and profile_qualified(caps)
             and catalog_complete and not caps["truncated"] and bool(caps["recipes"]))
    content_kind = profile_content_kind(caps)
    if not profile_qualified(caps):
        # The catalog is still observed; only the planner is withheld. The
        # reason names the observed profile kind so an operator can tell a
        # first-party expansion awaiting qualification from an unknown mod.
        reason = (
            "Profile/expansion/mod version not independently qualified "
            f"(observed content kind: {content_kind})"
        )
    elif not catalog_complete:
        reason = "Recipe catalog pages are not fully assembled"
    elif not ready:
        reason = "Recipe catalog empty/truncated: planning disabled"
    else:
        reason = "Read-only recipe catalog ready for qualified preview"
    return {"status": checked["status"], "planner_ready": ready,
            "reason": reason,
            "content_kind": content_kind,
            "mechanics": summary, "fingerprint": signature, "capabilities": caps,
            "catalog_status": catalog_status,
            # The observed supply is reported next to the theoretical
            # capabilities, never merged into them. A planner can therefore
            # tell "the recipe needs 100 iron plates" apart from "100 iron
            # plates are on hand right now".
            "observed_supply": supply.as_dict() if supply.known else None,
            "supply_observed": supply.known}


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
