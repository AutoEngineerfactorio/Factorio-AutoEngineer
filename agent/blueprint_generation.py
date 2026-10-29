"""Observed-mechanics blueprint layout generator and bounded production estimator.

This is the AI Helper's deterministic blueprint drafting path, not an LLM
hallucinating a factory: recipe, machine and crafting category must be
positively observed. Refuses probabilistic yields, missing speed, locked
recipes, unobserved machines and excessive counts. Export is an R07-validated
blueprint with the exact selected machine recipe; placement is never issued.
The generated spacing is a draft, NOT verified belt/fluid/power connectivity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from blueprint_document import describe
from blueprint_encoder import encode_document


class GenerationError(ValueError):
    """Observed data did not justify a buildable layout draft."""


MAX_MACHINES = 500
GAME_VERSION = (2 << 48) | (1 << 32) | (23 << 16)


@dataclass(frozen=True)
class ProductionDraft:
    document: dict
    recipe: str
    machine: str
    machine_count: int
    target_per_minute: float
    expected_per_minute: float
    source_fingerprint: str
    notes: tuple[str, ...]
    inputs_per_minute: tuple[tuple[str, float], ...]

    def exchange(self) -> str:
        return encode_document(self.document)


def _positive(value: Any, label: str) -> float:
    if (type(value) not in (int, float) or
            not math.isfinite(value) or value <= 0):
        raise GenerationError(f"{label} must be an observed positive finite number")
    return float(value)


def _part(row: Mapping[str, Any]) -> float:
    if row.get("deterministic") is False or row.get("probability") not in (None, 1, 1.0):
        raise GenerationError("Probabilistic outputs require a bounded planning mode")
    independent = row.get("independent_probability")
    if independent is not None and (
            type(independent) not in (int, float) or independent != 1):
        raise GenerationError("Independent probability does not guarantee a fixed yield")
    shared = row.get("shared_probability")
    if shared is not None and (
            not isinstance(shared, Mapping)
            or set(shared) != {"min", "max"}
            or any(type(shared[key]) not in (int, float) for key in ("min", "max"))
            or shared["min"] != 0 or shared["max"] != 1):
        raise GenerationError("Shared probability does not guarantee a fixed yield")
    if row.get("amount_min") is not None or row.get("amount_max") is not None:
        raise GenerationError("Variable recipe yields require a bounded planning mode")
    return _positive(row.get("amount"), "Recipe quantity")


def _categories(machine: Mapping[str, Any]) -> frozenset[str]:
    values = machine.get("crafting_categories")
    if values is None:
        values = machine.get("categories")
    if isinstance(values, Mapping):
        values = [k for k, v in values.items() if v]
    if not isinstance(values, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(x for x in values if isinstance(x, str) and x)


def generate_production_blueprint(
    recipe: Mapping[str, Any], machine: Mapping[str, Any],
    target_item: str, target_per_minute: float, *,
    source_fingerprint: str,
    grid_columns: int = 6,
) -> ProductionDraft:
    """Create one verified-recipe machine array, not a claimed finished factory.

    The caller supplies an actual R10-A observed recipe and compatible
    observed machine from the same catalog. No machine/category is guessed.
    """
    name = recipe.get("name")
    machine_name = machine.get("name")
    if not isinstance(name, str) or not name or not isinstance(machine_name, str) or not machine_name:
        raise GenerationError("Observed recipe and machine prototype names required")
    if recipe.get("enabled") is not True or recipe.get("hidden") is True:
        raise GenerationError("Recipe is not observed as enabled and visible")
    if not isinstance(source_fingerprint, str) or not source_fingerprint.strip():
        raise GenerationError("Complete observed catalog fingerprint is required")
    if not isinstance(target_item, str) or not target_item.strip():
        raise GenerationError("Target item or fluid must be observed")
    if not 1 <= grid_columns <= 25:
        raise GenerationError("Grid width must be 1-25")
    category = recipe.get("category")
    if not isinstance(category, str) or category not in _categories(machine):
        raise GenerationError("Machine compatibility with recipe category is not observed")
    speed = _positive(machine.get("crafting_speed"), "Crafting speed")
    seconds = _positive(recipe.get("crafting_time"), "Crafting time")
    amount = _positive(target_per_minute, "Production target per minute")
    products = recipe.get("products")
    if not isinstance(products, list):
        raise GenerationError("Observed recipe products are missing")
    target_rows = [p for p in products if isinstance(p, Mapping) and
                   p.get("name") == target_item]
    if len(target_rows) != 1:
        raise GenerationError("Target must match exactly one observed recipe product")
    yield_per_craft = _part(target_rows[0])
    production_each = speed / seconds * yield_per_craft * 60
    machines = math.ceil(amount / production_each)
    if not 1 <= machines <= MAX_MACHINES:
        raise GenerationError("Required machines exceed safe layout limit")
    inputs = recipe.get("ingredients")
    if not isinstance(inputs, list):
        raise GenerationError("Recipe ingredients are not observed")
    inputs_per_minute = []
    for entry in inputs:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
            raise GenerationError("An ingredient is missing its observed name")
        quantity = _positive(entry.get("amount"), "Ingredient amount")
        inputs_per_minute.append((
            str(entry["name"]),
            round(quantity * amount / yield_per_craft, 6),
        ))
    # A grid of actual selected recipe machines. Position spacing is safe
    # enough for *preview*, but dimensions/ports are not universally known.
    # Never claim it is a complete throughput-balanced connected factory.
    entities = []
    for i in range(machines):
        column, row = i % grid_columns, i // grid_columns
        entities.append({
            "entity_number": i + 1,
            "name": machine_name,
            "position": {"x": column * 10, "y": row * 10},
            "recipe": name,
        })
    document = {"blueprint": {
        "item": "blueprint",
        "label": f"{target_item} - {machines}x {machine_name}",
        "description": (
            f"AutoEngineer observed recipe draft; target {amount:g}/min. "
            "Machine spacing, fluid ports, power and logistics NOT verified."
        ),
        "version": GAME_VERSION,
        "entities": entities,
    }}
    describe(document)
    return ProductionDraft(
        document=document, recipe=name, machine=machine_name,
        machine_count=machines, target_per_minute=amount,
        expected_per_minute=round(production_each * machines, 6),
        source_fingerprint=source_fingerprint,
        notes=(
            "Recipe and machine category verified from one observed catalog",
            "The machine layout is a draft; not a full connected/validated factory",
            "Belts, inserters, fluid ports, electricity and logistics still need layout solving",
            "No game placement, no research changes and no fabricated prototype data",
        ),
        inputs_per_minute=tuple(inputs_per_minute),
    )
