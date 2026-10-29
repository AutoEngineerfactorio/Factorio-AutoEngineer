"""Observed-catalog adapter for bounded flow estimates, never gameplay permission."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Mapping

from effective_yield import yield_of_part
from production_flow import FlowProcess, FlowRequest, nonnegative, solve_flow


def material(part: Mapping[str, Any]) -> str:
    if part.get("type") not in ("item", "fluid") or not isinstance(part.get("name"), str):
        raise ValueError("Observed item/fluid identity required")
    return str(part["type"]) + ":" + part["name"]


def recipe_flow(recipe: Mapping[str, Any], allow_expected: bool):
    inputs: dict[str, float] = {}
    outputs: dict[str, float] = {}
    basis = "deterministic"
    for group, destination in (("ingredients", inputs), ("products", outputs)):
        for part in recipe.get(group, ()):
            if any(key in part for key in ("temperature", "minimum_temperature", "maximum_temperature",
                                           "quality_min", "quality_max", "quality_change")):
                raise ValueError("Thermal/quality routing is not qualified")
            # Normal quality with zero quality bonus yields normal outputs even
            # when the prototype permits quality effects. Non-normal routes
            # remain excluded above; no quality bonus is applied here.
            if part.get("percent_spoiled", 0):
                raise ValueError("Spoilage mechanics are not qualified")
            key = material(part)
            if group == "ingredients":
                amount = nonnegative(part.get("amount"))
            else:
                value = yield_of_part(dict(part))
                if value.deterministic:
                    amount = value.guaranteed
                elif allow_expected and value.expected is not None:
                    amount = value.expected
                    basis = "expected"
                else:
                    raise ValueError("Output requires an explicitly accepted, known expectation")
                if amount is None or amount <= 0:
                    raise ValueError("Output amount is not qualified")
            destination[key] = destination.get(key, 0) + amount
    if not inputs:
        raise ValueError("Source recipe requires a separately observed extraction adapter")
    return inputs, outputs, basis


def observed_processes(snapshot: Any, request: FlowRequest, *, allow_expected: bool = False,
                       machine_limits: Mapping[str, int] | None = None):
    """Expand upstream alternatives only; keep exclusions and machine evidence explicit."""
    if snapshot is None or not snapshot.complete or snapshot.game_version != "2.1.23":
        raise ValueError("Complete current 2.1.23 observed catalog required")
    known_materials = {material(part) for recipe in snapshot.recipes
                       for group in ("ingredients", "products") for part in recipe.get(group, ())}
    requested = set(request.demands) | set(request.supplies) | set(request.surplus_capacity) | set(request.seed_inventory)
    if requested - known_materials:
        raise ValueError("Material identity not present in the observed catalog")
    candidates, excluded = {}, {}
    producers: dict[str, list[str]] = defaultdict(list)
    for recipe in snapshot.recipes:
        if recipe.get("enabled") is not True or recipe.get("hidden") is True:
            continue
        try:
            inputs, outputs, basis = recipe_flow(recipe, allow_expected)
            duration = nonnegative(recipe.get("crafting_time"))
            if duration <= 0:
                raise ValueError("Positive crafting time required")
        except (ValueError, TypeError) as exc:
            excluded[str(recipe.get("name"))] = str(exc)
            continue
        candidates[recipe["name"]] = (recipe, inputs, outputs, basis, duration)
        for output in outputs:
            producers[output].append(recipe["name"])
    needed, visited, selected = deque(request.demands), set(), set()
    while needed:
        output = needed.popleft()
        if output in visited or request.supplies.get(output, 0) > 0:
            continue
        visited.add(output)
        for name in producers.get(output, ()):
            if name not in selected:
                selected.add(name)
                needed.extend(candidates[name][1])
    processes, power_known = [], True
    for name in sorted(selected):
        recipe, inputs, outputs, basis, duration = candidates[name]
        categories = set(recipe.get("categories") or [recipe.get("category")])
        for machine in snapshot.machines:
            if not categories.intersection(machine.get("crafting_categories", ())):
                continue
            speed, watts = machine.get("crafting_speed"), machine.get("energy_usage")
            if speed is None or watts is None or speed <= 0:
                continue
            drain = machine.get("energy_drain")
            power_known = power_known and drain is not None
            if request.power_budget_watts is not None and drain is None:
                continue
            limit = machine_limits.get(machine["name"], 0) if machine_limits is not None else 1000000
            processes.append(FlowProcess(name + " @ " + machine["name"], inputs, outputs,
                speed / duration, watts, drain or 0, limit, basis=basis, machine_group=machine["name"]))
            if len(processes) > 10000:
                raise ValueError("Observed recipe/machine alternative budget exceeded")
    return processes, excluded, power_known


def solve_observed_flow(snapshot: Any, request: FlowRequest, *, allow_expected: bool = False,
                        machine_limits=None, objective="machines") -> dict:
    processes, excluded, power_known = observed_processes(snapshot, request,
        allow_expected=allow_expected, machine_limits=machine_limits)
    result = solve_flow(processes, request, objective=objective, machine_limits=machine_limits)
    result.update(source_fingerprint=snapshot.source_fingerprint, game_version=snapshot.game_version,
        catalog_exclusions=len(snapshot.excluded), adapter_exclusions=excluded,
        power_includes_observed_drain=power_known,
        assumptions="Normal quality and base recipe yields, no productivity/quality/module/beacon bonuses; surface, fuel, transport, spoilage lifetime and machine availability require separate validation")
    if not power_known and "working_and_idle_watts" in result:
        result["working_watts_excluding_unknown_drain"] = result.pop("working_and_idle_watts")
    return result
