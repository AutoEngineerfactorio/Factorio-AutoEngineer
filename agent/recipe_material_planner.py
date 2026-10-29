"""Bounded read-only material requirements from an observed recipe catalog."""

import math

from effective_yield import (
    combined_target_yield,
    uncertainty_summary,
    yield_of_part,
    yield_of_products,
)
from production_solver import compute_target_production
from read_only_planning import bounded_name, validate_capabilities
from recipe_feasibility import STATUS_AVAILABLE, STATUS_LOCKED, assess_recipes

MAX_PLAN_NODES = 256
MAX_PLAN_DEPTH = 32
MAX_QUANTITY = 1e12
MATERIAL_TYPES = frozenset({"item", "fluid"})


def _material_key(material_type, name):
    return material_type, name


def _display_key(key):
    return f"{key[0]}:{key[1]}"


def plan_product_materials(intelligence, material_type, name, amount: float = 1, *, choices=None):
    """Expand a target into recipe requirements without claiming feasibility.

    Recipe choices map ``"type:name"`` to an observed recipe name. Products
    other than the target are reported as uncredited co-products; they are not
    used to reduce another branch's requirements.
    """
    if not isinstance(intelligence, dict) or intelligence.get("planner_ready") is not True:
        raise ValueError("A qualified complete recipe catalog is required")
    capabilities = intelligence.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities.get("source_fingerprint"):
        raise ValueError("A fingerprinted recipe catalog is required")
    capabilities = validate_capabilities(
        capabilities, capabilities.get("surface"), capabilities.get("tick")
    )
    if not isinstance(material_type, str) or material_type not in MATERIAL_TYPES:
        raise ValueError("Target type must be item or fluid")
    name = bounded_name(name)
    if (type(amount) not in (int, float) or not math.isfinite(amount)
            or amount <= 0 or amount > MAX_QUANTITY):
        raise ValueError("Target amount must be finite, positive, and bounded")
    if choices is None:
        choices = {}
    if not isinstance(choices, dict) or len(choices) > MAX_PLAN_NODES:
        raise ValueError("Recipe choices must be a bounded mapping")
    normalized_choices = {}
    for key, recipe_name in choices.items():
        if not isinstance(key, str) or ":" not in key:
            raise ValueError("Recipe choice keys must be type:name")
        choice_type, choice_name = key.split(":", 1)
        if choice_type not in MATERIAL_TYPES:
            raise ValueError("Recipe choice type must be item or fluid")
        normalized_choices[_material_key(choice_type, bounded_name(choice_name))] = (
            bounded_name(recipe_name)
        )

    recipes = capabilities["recipes"]
    candidates = {}
    disabled = {}
    locked = {}
    recipes_by_name = {}
    # The researched technology set is what decides whether an unlock
    # technology has been satisfied. The backend reports the unlock
    # technologies of every recipe, and the researched set separately.
    observed_research: set[str] = set(capabilities.get("research") or ())
    feasibility = assess_recipes(recipes, observed_research)
    for recipe in recipes:
        recipes_by_name[recipe["name"]] = recipe
        entry = feasibility[recipe["name"]]
        if entry.status == STATUS_AVAILABLE:
            index = candidates
        elif entry.status == STATUS_LOCKED:
            index = locked
        else:
            index = disabled
        for product in recipe["products"]:
            key = _material_key(product["type"], product["name"])
            index.setdefault(key, set()).add(recipe["name"])
    for key, recipe_name in normalized_choices.items():
        if recipe_name not in candidates.get(key, ()):
            raise ValueError(
                f"Selected recipe is not enabled for {_display_key(key)}"
            )

    selected = {}
    unresolved = {}
    coproducts = {}
    coproduct_yields = {}
    uncertain_recipes = {}
    active = []
    visited_nodes = 0
    limit_hit = False

    def add_unresolved(key, quantity, reason, candidate_names=()):
        nonlocal limit_hit
        item_key = (key, reason, tuple(candidate_names))
        entry = unresolved.setdefault(
            item_key,
            {"type": key[0], "name": key[1], "amount": 0.0,
             "reason": reason, "candidates": list(candidate_names)},
        )
        total = entry["amount"] + quantity
        if math.isfinite(total) and total <= MAX_QUANTITY:
            entry["amount"] = total
        else:
            limit_hit = True
            entry["reason"] = "quantity budget exceeded"
            entry["amount"] = min(entry["amount"], MAX_QUANTITY)

    def add_coproduct(recipe_name, product, batches):
        nonlocal limit_hit
        key = (recipe_name, product["type"], product["name"])
        product_yield = yield_of_part(product)
        # A co-product with an uncertain yield is reported with its bounds
        # and its expectation, never as one falsely precise number.
        quantity = (
            product_yield.expected if product_yield.expected is not None
            else product_yield.amount
        ) * batches
        if not math.isfinite(quantity) or quantity > MAX_QUANTITY:
            limit_hit = True
            add_unresolved(
                _material_key(product["type"], product["name"]),
                0.0,
                "quantity budget exceeded",
            )
            return
        entry = coproducts.setdefault(
            key,
            {"recipe": recipe_name, "type": product["type"], "name": product["name"],
             "amount": 0.0},
        )
        total = entry["amount"] + quantity
        if not math.isfinite(total) or total > MAX_QUANTITY:
            limit_hit = True
            add_unresolved(
                _material_key(product["type"], product["name"]),
                0.0,
                "quantity budget exceeded",
            )
            return
        entry["amount"] = total
        # The yield description is kept in a separate map so the established
        # co-product row shape is unchanged.
        coproduct_yields[key] = product_yield.as_dict()

    def expand(key, quantity, depth):
        nonlocal visited_nodes, limit_hit
        if not math.isfinite(quantity) or quantity > MAX_QUANTITY:
            limit_hit = True
            add_unresolved(key, 0.0, "quantity budget exceeded")
            return
        if key in active:
            cycle = active[active.index(key):] + [key]
            add_unresolved(
                key, quantity, "recipe cycle: " + " -> ".join(_display_key(v) for v in cycle)
            )
            return
        if depth > MAX_PLAN_DEPTH or visited_nodes >= MAX_PLAN_NODES:
            limit_hit = True
            add_unresolved(key, quantity, "planning complexity limit reached")
            return
        visited_nodes += 1

        available_names = sorted(candidates.get(key, ()))
        if not available_names:
            locked_names = sorted(locked.get(key, ()))
            disabled_names = sorted(disabled.get(key, ()))
            if locked_names:
                # The recipe exists but an unlock technology has not been
                # researched yet, so it cannot be planned now.
                blockers = sorted({
                    blocker
                    for name in locked_names
                    for blocker in feasibility[name].blocked_by
                })
                add_unresolved(
                    key, quantity,
                    "no unlocked recipe candidate; the unlock technology is not "
                    "researched: " + ", ".join(blockers),
                    locked_names,
                )
            elif disabled_names:
                reason = "only hidden or disabled recipe candidates were observed"
                if any(recipes_by_name[item]["enabled"] is False for item in disabled_names):
                    reason = "no currently enabled recipe; observed candidates are disabled or hidden"
                add_unresolved(key, quantity, reason, disabled_names)
            else:
                add_unresolved(
                    key, quantity,
                    "no recipe output observed; external supply/buildability is unknown",
                )
            return

        selected_name = normalized_choices.get(key)
        if selected_name is None and len(available_names) == 1:
            selected_name = available_names[0]
        if selected_name not in available_names:
            add_unresolved(
                key, quantity,
                "multiple enabled recipe candidates require an explicit choice",
                available_names,
            )
            return

        recipe = recipes_by_name[selected_name]
        # The batch count must come from the effective yield, not from the
        # nominal amount. A ranged or probabilistic product has no single
        # guaranteed amount, so the batch count would be falsely precise.
        target_yield = combined_target_yield(
            recipe["products"], key[0], key[1]
        )
        matching_output = target_yield.guaranteed
        if matching_output is None:
            # The yield is uncertain. The recipe is still reported so the
            # user sees its bounds, but the requirement is not expanded from
            # a guessed amount.
            uncertain_recipes[selected_name] = target_yield
            add_unresolved(
                key, quantity,
                "selected recipe output yield is uncertain: "
                + "; ".join(target_yield.reasons)
                if target_yield.reasons
                else "selected recipe output yield is uncertain",
            )
            return
        if not math.isfinite(matching_output) or matching_output <= 0:
            add_unresolved(key, quantity, "selected recipe has no valid target output")
            return
        batches = quantity / matching_output
        if not math.isfinite(batches) or batches > MAX_QUANTITY:
            limit_hit = True
            add_unresolved(key, quantity, "quantity budget exceeded")
            return

        active.append(key)
        selected_batches = selected.get(selected_name, 0.0) + batches
        if not math.isfinite(selected_batches) or selected_batches > MAX_QUANTITY:
            limit_hit = True
            active.pop()
            add_unresolved(key, quantity, "quantity budget exceeded")
            return
        selected[selected_name] = selected_batches
        for product in recipe["products"]:
            product_key = _material_key(product["type"], product["name"])
            if product_key != key:
                add_coproduct(selected_name, product, batches)

        if not recipe["ingredients"]:
            add_unresolved(
                key, quantity,
                "recipe has no modeled source input; sustainable supply is unknown",
            )
        else:
            for ingredient in recipe["ingredients"]:
                child = _material_key(ingredient["type"], ingredient["name"])
                expand(child, ingredient["amount"] * batches, depth + 1)
        active.pop()

    target = _material_key(material_type, name)
    expand(target, float(amount), 0)

    unresolved_rows = sorted(
        unresolved.values(),
        key=lambda row: (
            row["type"], row["name"], row["reason"], tuple(row["candidates"])
        ),
    )
    selected_rows = [
        {"recipe": recipe_name, "batches": batches}
        for recipe_name, batches in sorted(selected.items())
    ]
    selected_details = []
    yield_uncertainty: list[str] = []
    detail_rows = list(selected_rows) + [
        {"recipe": name, "batches": 0.0}
        for name in sorted(uncertain_recipes)
        if name not in selected
    ]
    for row in detail_rows:
        recipe = recipes_by_name[row["recipe"]]
        product_yields = yield_of_products(recipe["products"])
        ingredient_yields = [yield_of_part(value) for value in recipe["ingredients"]]
        for reason in uncertainty_summary(product_yields + ingredient_yields):
            if reason not in yield_uncertainty:
                yield_uncertainty.append(reason)
        selected_details.append({
            **row,
            "category": recipe["category"],
            "crafting_time_seconds": recipe["crafting_time"],
            "ingredients_per_craft": [dict(value) for value in recipe["ingredients"]],
            "products_per_craft": [dict(value) for value in recipe["products"]],
            "product_yields": [value.as_dict() for value in product_yields],
            "ingredient_yields": [value.as_dict() for value in ingredient_yields],
            "target_yield": combined_target_yield(
                recipe["products"], target[0], target[1]
            ).as_dict(),
        })
    coproduct_rows = [
        coproducts[key] for key in sorted(coproducts)
    ]
    ambiguities = [
        dict(row) for row in unresolved_rows
        if row["reason"].startswith("multiple enabled recipe candidates")
    ]
    unlock_limitations = [
        dict(row) for row in unresolved_rows
        if row["candidates"] and any(
            not recipes_by_name[name]["enabled"] for name in row["candidates"]
        )
    ]
    research_limitations = [
        dict(row) for row in unresolved_rows
        if row["candidates"] and any(
            feasibility[name].status == STATUS_LOCKED for name in row["candidates"]
        )
    ]
    feasibility_rows = [
        {"recipe": name, **feasibility[name].as_dict()}
        for name in sorted(feasibility)
    ]
    unsupported_mechanics = sorted({
        row["reason"] for row in unresolved_rows
        if (row["reason"].startswith("recipe cycle:")
            or row["reason"].startswith("selected recipe output yield is uncertain")
            or row["reason"] in {
                "planning complexity limit reached", "quantity budget exceeded"})
    })
    # The yield mechanics that are observed but not exactly modelled are
    # reported explicitly instead of being hidden behind a confident number.
    for reason in yield_uncertainty:
        if reason not in unsupported_mechanics:
            unsupported_mechanics.append(reason)
    unsupported_mechanics.sort()
    if (limit_hit or any(
            row["reason"].startswith("recipe cycle:") for row in unresolved_rows
    )):
        status = "unsupported"
    elif unresolved_rows:
        status = "partial"
    else:
        status = "estimated"
    return {
        "status": status,
        "target": {"type": material_type, "name": name, "amount": float(amount)},
        "selected_recipes": selected_rows,
        "selected_recipe_details": selected_details,
        "unresolved": unresolved_rows,
        "recipe_ambiguities": ambiguities,
        "research_unlock_limitations": unlock_limitations,
        "research_lock_limitations": research_limitations,
        "recipe_feasibility": feasibility_rows,
        "uncredited_coproducts": coproduct_rows,
        "coproduct_yields": {
            f"{recipe_name}|{material_type}:{material_name}": data
            for (recipe_name, material_type, material_name), data
            in sorted(coproduct_yields.items())
        },
        "coproduct_credit_policy": "reported-only; no requirement credits applied",
        "unsupported_mechanics": unsupported_mechanics,
        "yield_uncertainty": list(yield_uncertainty),
        "uncertainty": [dict(row) for row in unresolved_rows],
        "source": {
            "game_version": capabilities["game_version"],
            "fingerprint": capabilities["source_fingerprint"],
            "force": capabilities["force"],
            "surface": capabilities["surface"],
            "tick": capabilities["tick"],
            "enabled_content": list(capabilities["enabled_content"]),
            "observed_research": list(capabilities["research"]),
        },
        "throughput_status": "not-computed",
        "physical_buildability_verified": False,
        "notes": [
            "Offline material requirements only; no machine, throughput, power, "
            "transport, buffer, or buildability claim.",
            "Co-products are reported but not credited against other requirements.",
            "Recipe alternatives are not optimized; ambiguous choices require an explicit selection.",
            *(
                ["Batch counts use the guaranteed yield; an uncertain yield is "
                 "reported with its bounds and is not expanded."]
                if yield_uncertainty else []
            ),
        ],
    }


def plan_target_production(
    intelligence,
    material_type: str,
    name: str,
    *,
    per_second=None,
    per_minute=None,
    machine_speed=None,
    machine_name=None,
    machine_energy_kw=None,
):
    """Plan the production of one target at a requested rate.

    The rate is stated in items per second **or** in items per minute. The
    returned plan reports the achievable rate, the machine count and the
    alternative production paths when the observed data establishes them.

    The observed recipe catalog reports a recipe's **crafting category** and
    its **crafting time**, but it does not report which machine would run the
    recipe and at what speed. A machine count therefore needs an established
    machine speed; without one the plan reports the craft rate as unsupported
    instead of inventing a machine.
    """
    if not isinstance(intelligence, dict) or intelligence.get("planner_ready") is not True:
        raise ValueError("A qualified complete recipe catalog is required")
    capabilities = intelligence.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities.get("source_fingerprint"):
        raise ValueError("A fingerprinted recipe catalog is required")
    capabilities = validate_capabilities(
        capabilities, capabilities.get("surface"), capabilities.get("tick")
    )
    if not isinstance(material_type, str) or material_type not in MATERIAL_TYPES:
        raise ValueError("Target type must be item or fluid")
    name = bounded_name(name)

    observed_research: set[str] = set(capabilities.get("research") or ())
    feasibility = assess_recipes(capabilities["recipes"], observed_research)
    # Only a recipe that is currently usable may be a production path. A
    # locked or disabled recipe is reported as an alternative only when it is
    # actually unlocked, so the plan never offers a recipe the profile cannot
    # build yet.
    usable = [
        recipe for recipe in capabilities["recipes"]
        if feasibility[recipe["name"]].status == STATUS_AVAILABLE
    ]
    locked = [
        recipe for recipe in capabilities["recipes"]
        if feasibility[recipe["name"]].status == STATUS_LOCKED
    ]

    result = compute_target_production(
        usable,
        material_type,
        name,
        per_second=per_second,
        per_minute=per_minute,
        machine_speed=machine_speed,
        machine_name=machine_name,
        machine_energy_kw=machine_energy_kw,
    )
    data = result.as_dict()

    # "No observed recipe produces this target" and "no *usable* recipe
    # produces it" are different facts and must not collapse into one.
    # The solver only sees the usable recipes, so the distinction is made
    # here, where every observed recipe is still in hand.
    observed_producers = [
        recipe for recipe in capabilities["recipes"]
        if any(
            part.get("type") == material_type and part.get("name") == name
            for part in recipe["products"]
        )
    ]
    if not observed_producers and data["status"] == "unsupported":
        data["status"] = "unavailable"
        data["unsupported"] = [
            "no observed recipe produces this target"
        ] + [
            reason for reason in data["unsupported"]
            if reason != "no observed recipe produces this target"
        ]
    elif observed_producers and not usable:
        data["status"] = "unavailable"
        data["unsupported"] = [
            "every observed recipe for this target is locked, disabled or hidden"
        ]

    locked_names = sorted(
        recipe["name"] for recipe in locked
        if any(
            part.get("type") == material_type and part.get("name") == name
            for part in recipe["products"]
        )
    )
    if locked_names:
        data["locked_alternative_paths"] = locked_names
        data["unsupported"] = list(data["unsupported"]) + [
            "some observed production paths for this target are locked behind "
            "an unresearched technology and are not counted as usable paths"
        ]
    else:
        data["locked_alternative_paths"] = []

    data["status"] = str(data["status"])
    data["throughput_status"] = "estimated-from-observed-catalog"
    data["physical_buildability_verified"] = False
    data["source"] = {
        "game_version": capabilities["game_version"],
        "fingerprint": capabilities["source_fingerprint"],
        "force": capabilities["force"],
        "surface": capabilities["surface"],
        "tick": capabilities["tick"],
    }
    return data


def format_target_production(plan):
    """Format a production-target plan for the read-only details pane."""
    lines = [
        f"Production target: {plan['status']}",
        f"Target: {plan['target_type']}:{plan['target']}",
        f"Requested: {plan['requested_per_second']:g} /s "
        f"({plan['requested_per_minute']:g} /min)",
    ]
    if plan.get("recipe"):
        lines.append(f"Recipe: {plan['recipe']}")
    if plan.get("achievable_per_second") is not None:
        lines.append(
            f"Achievable: {plan['achievable_per_second']:g} /s "
            f"({plan['achievable_per_minute']:g} /min)"
        )
    if plan.get("machine_count") is not None:
        lines.append(
            f"Machine count: {plan['machine_count']:g}"
            + (f" x {plan['machine_name']}" if plan.get("machine_name") else "")
        )
    if plan.get("power_kw") is not None:
        lines.append(f"Power: {plan['power_kw']:g} kW")
    if plan.get("output_per_craft") is not None:
        lines.append(f"Output per craft: {plan['output_per_craft']:g}")
    if plan.get("output_minimum") is not None or plan.get("output_maximum") is not None:
        lines.append(
            f"Output bounds: min {plan.get('output_minimum')}, "
            f"max {plan.get('output_maximum')}"
        )
    if plan.get("output_probability") is not None:
        lines.append(f"Output probability: {plan['output_probability']:g}")
    if plan.get("alternatives"):
        lines.append("Alternative production paths:")
        lines.extend(
            f"- {row['recipe']}: {row['units_per_second']:g} /s "
            f"({row['units_per_minute']:g} /min)"
            + (f", machines {row['machine_count']:g}"
               if row.get("machine_count") is not None else "")
            for row in plan["alternatives"]
        )
    if plan.get("locked_alternative_paths"):
        lines.append("Observed but research-locked paths:")
        lines.extend(
            f"- {name} (not researched)" for name in plan["locked_alternative_paths"]
        )
    if plan.get("unsupported"):
        lines.append("Not established:")
        lines.extend(f"- {reason}" for reason in plan["unsupported"])
    return "\n".join(lines)


def format_material_plan(plan):
    """Format a material plan for the read-only dashboard details pane."""
    target = plan["target"]
    lines = [
        f"Material requirements: {plan['status']}",
        f"Target: {target['amount']:g} {target['type']}:{target['name']}",
    ]
    if plan["selected_recipes"]:
        lines.append("Recipe batches (fractional; no machine rounding):")
        lines.extend(
            f"- {row['recipe']}: {row['batches']:g} batches"
            for row in plan["selected_recipes"]
        )
    if plan["unresolved"]:
        lines.append("Unresolved requirements:")
        lines.extend(
            f"- {row['amount']:g} {row['type']}:{row['name']} — {row['reason']}"
            + (f" [{', '.join(row['candidates'])}]" if row["candidates"] else "")
            for row in plan["unresolved"]
        )
    if plan["uncredited_coproducts"]:
        lines.append("Uncredited co-products:")
        lines.extend(
            f"- {row['amount']:g} {row['type']}:{row['name']} from {row['recipe']}"
            for row in plan["uncredited_coproducts"]
        )
        for key, data in plan.get("coproduct_yields", {}).items():
            if not data.get("is_uncertain"):
                continue
            lines.append(f"- {key} has an uncertain yield: "
                         + "; ".join(data.get("reasons", [])))
    if plan.get("yield_uncertainty"):
        lines.append("Uncertain output mechanics:")
        lines.extend(f"- {reason}" for reason in plan["yield_uncertainty"])
    for row in plan.get("selected_recipe_details", ()):
        target_yield = row.get("target_yield")
        if not target_yield or not target_yield.get("is_uncertain"):
            continue
        bounds = []
        if target_yield.get("minimum") is not None:
            bounds.append(f"min {target_yield['minimum']:g}")
        if target_yield.get("maximum") is not None:
            bounds.append(f"max {target_yield['maximum']:g}")
        if target_yield.get("probability") is not None:
            bounds.append(f"probability {target_yield['probability']:g}")
        lines.append(
            f"- {row['recipe']} output yield is uncertain"
            + (f" ({', '.join(bounds)})" if bounds else "")
        )
    lines.extend(("", *plan["notes"]))
    return "\n".join(lines)
