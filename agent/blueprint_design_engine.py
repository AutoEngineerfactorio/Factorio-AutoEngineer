"""Bounded observation-driven Factorio blueprint *draft* generator.

Only verified catalog recipe names and compatible machine prototypes become
entities; no guessed belts, pipe ports, inserters, power or logistics. The
result is an R07-validated exchange-ready machine layout, explicitly NOT a
fully routed or tested factory.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from blueprint_document import decode
from blueprint_encoder import encode_document
from blueprint_spatial_layout import LayoutError, plan_layout

MAX_DRAFT_MACHINES = 256
MAX_COLUMNS = 12
MAX_SPACING = 32


def game_version_code(value: str) -> int:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?", value)
    if match is None:
        raise ValueError("A verified game version is required")
    parts = [int(x) if x is not None else 0 for x in match.groups()]
    if any(not 0 <= x < 65536 for x in parts):
        raise ValueError("Game version component out of bounds")
    return sum(part << shift for part, shift in
               zip(parts, (48, 32, 16, 0)))


def generate_draft(plan: Mapping[str, Any], *, spacing: int = 8,
                   columns: int = MAX_COLUMNS) -> dict[str, Any]:
    if (type(spacing) is not int or not 4 <= spacing <= MAX_SPACING
            or type(columns) is not int or not 1 <= columns <= MAX_COLUMNS):
        raise ValueError("Spacing/columns must be within bounded layout limits")
    recipe = plan.get("recipe")
    machine = plan.get("machine")
    if not isinstance(recipe, Mapping) or not isinstance(machine, Mapping):
        raise ValueError("Observed recipe and compatible machine are required")
    name, prototype = recipe.get("name"), machine.get("name")
    if (not isinstance(name, str) or not name
            or not isinstance(prototype, str) or not prototype):
        raise ValueError("Blueprint requires observed names")
    categories = recipe.get("categories") or [recipe.get("category")]
    allowed = machine.get("crafting_categories")
    if (not isinstance(categories, (list, tuple))
            or not isinstance(allowed, (list, tuple))
            or not set(categories).intersection(allowed)):
        raise ValueError("Machine has no observed matching crafting category")
    count = plan.get("machine_count")
    if type(count) is not int or not 1 <= count <= MAX_DRAFT_MACHINES:
        raise ValueError("Machine quantity unavailable or exceeds draft limit")
    if plan.get("status") != "estimated":
        raise ValueError("A qualified estimated R06 production plan is required")
    fingerprint = plan.get("source_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError("A fingerprinted observed catalog is required")
    version = game_version_code(str(plan.get("game_version") or ""))
    layout = None
    layout_error = None
    if isinstance(machine.get("size"), Mapping):
        # The observation describes the machine footprint, so the layout can
        # be derived from it instead of from a uniform grid. A footprint
        # that the observation cannot justify is refused here instead of
        # falling back to a guess.
        try:
            layout = plan_layout(
                recipe, machine,
                machine_count=count,
                crafting_speed=machine.get("crafting_speed"),
                crafting_time=recipe.get("crafting_time"),
                energy_usage=machine.get("energy_usage"),
                columns=min(columns, MAX_COLUMNS),
            )
        except LayoutError as error:
            layout_error = str(error)
            layout = None
    if layout is not None:
        entities = [
            {
                "entity_number": placement.entity_number,
                "name": placement.name,
                "position": dict(placement.position),
                "recipe": placement.recipe,
                "direction": placement.direction,
            }
            for placement in layout.placements
        ]
    else:
        entities = [{
            "entity_number": index + 1,
            "name": prototype,
            "position": {
                "x": (index % columns) * spacing,
                "y": (index // columns) * spacing,
            },
            "recipe": name,
        } for index in range(count)]
    target = plan.get("target")
    product = target.get("name") if isinstance(target, Mapping) else name
    label = f"{product} - {count}x {prototype}"[:100]
    doc = {"blueprint": {
        "version": version,
        "label": label,
        "description": (
            "AutoEngineer observed-plan machine-layout DRAFT. "
            "No input/output routing, electric poles, logistics, fluid pipes, "
            "collision, modules, beacons, quality or buildability verified."),
        "entities": entities,
    }}
    encoded = encode_document(doc)
    if decode(encoded) != doc:
        raise ValueError("Generated document did not round trip")
    warnings = [
        "Machine prototypes and recipes came from the observed game catalog.",
        "Recipe assignment must be verified on imported entity types.",
        "Physical size, collisions, fluids, inputs/outputs and power not planned.",
        "This is not a working factory blueprint or an LLM-authored layout.",
    ]
    result: dict[str, Any] = {
        "document": doc,
        "exchange": encoded,
        "machine_count": count,
        "status": "draft_not_buildability_verified",
        "source_fingerprint": fingerprint,
        "warnings": warnings,
    }
    if layout is not None:
        # The layout was derived from the observed footprint and the
        # observed recipe. It is still a draft: the belts, inserters, pipes
        # and the power grid are not placed and the game never saw it.
        result["status"] = "draft_spatial_plan_validated"
        result["warnings"] = [
            "Machine prototypes and recipes came from the observed game catalog.",
            "Entity positions were derived from the observed machine size.",
            "Ingredient and product flows were derived from the observed recipe.",
            "Belts, inserters, pipes, poles, the power grid and the buildability "
            "in the game are NOT verified.",
        ]
        result["layout"] = {
            "inputs": [
                {"item": c.item, "per_minute": c.amount_per_minute,
                 "fluid": c.fluid}
                for c in layout.inputs
            ],
            "outputs": [
                {"item": c.item, "per_minute": c.amount_per_minute,
                 "fluid": c.fluid}
                for c in layout.outputs
            ],
            "power_watts": layout.power_watts,
        }
    elif layout_error is not None:
        result["warnings"] = warnings + [
            f"The observed footprint was unusable, so the uniform grid was "
            f"kept: {layout_error}",
        ]
    return result
