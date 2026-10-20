"""Bounded read-only material requirements from an observed recipe catalog."""

import math

from read_only_planning import bounded_name, validate_capabilities

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
    recipes_by_name = {}
    for recipe in recipes:
        recipes_by_name[recipe["name"]] = recipe
        index = candidates if recipe["enabled"] and not recipe["hidden"] else disabled
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
        quantity = product["amount"] * batches
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
            disabled_names = sorted(disabled.get(key, ()))
            if disabled_names:
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
        matching_output = sum(
            product["amount"] for product in recipe["products"]
            if (product["type"], product["name"]) == key
        )
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
    coproduct_rows = [
        coproducts[key] for key in sorted(coproducts)
    ]
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
        "unresolved": unresolved_rows,
        "uncredited_coproducts": coproduct_rows,
        "notes": [
            "Offline material requirements only; no machine, throughput, power, "
            "transport, buffer, or buildability claim.",
            "Co-products are reported but not credited against other requirements.",
            "Recipe alternatives are not optimized; ambiguous choices require an explicit selection.",
        ],
    }


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
    lines.extend(("", *plan["notes"]))
    return "\n".join(lines)
