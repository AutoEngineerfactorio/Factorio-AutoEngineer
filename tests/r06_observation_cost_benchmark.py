"""Measure the CPU cost of the observation path that runs on every poll.

This is an OFFLINE benchmark. It executes the **real** adapter Lua from
``backend-safety/Tools/RecipeResearchAdapter.cs`` against a synthetic force
whose size matches the observed live Pyanodons catalog (10,146 recipes,
256 machines), and measures the wall time of the work that a single
``autoengineer_view`` poll performs.

It measures the **Lua-side** cost only. It never contacts the game, never
starts Factorio and never touches a save. Factorio's own UPS impact is
measured separately, under an authorized live session.

Run it directly::

    python -B tests/r06_observation_cost_benchmark.py

The numbers are printed as JSON so a later report can quote them without
re-running anything.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"

#: The observed live Pyanodons catalog size, from the recorded R06 sweeps
#: (``r06-live-sweep-007.json``): ``total_count`` 10146 and 256 machines.
OBSERVED_RECIPE_COUNT = 10146
OBSERVED_MACHINE_COUNT = 256


def _adapter_lua() -> str:
    """Return the adapter's whole catalog Lua literal, de-indented."""
    source = ADAPTER.read_text(encoding="utf-8")
    marker = "$" * 3 + '"' * 3
    start = source.index(marker) + len(marker)
    end = source.index('"' * 3, start)
    block = source[start:end]
    block = block.replace("{{{pageSize}}}", "32")
    block = block.replace("{{{page}}}", "PAGE")
    block = re.sub(r"\{\{\{\(catalogOnly[^\n]*?\}\}\}", "true", block)
    if "{{{" in block:
        raise AssertionError("an unresolved interpolation placeholder remains")
    lines = block.split("\n")
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    trim = min(indents) if indents else 0
    return "\n".join(line[trim:] if len(line) >= trim else line for line in lines)


#: A synthetic force with the observed live scale.
#:
#: The shape is the one the live 2.1.23 server exposes: ``force.recipes``
#: is a table of recipes, each with ``enabled``, ``hidden``, ``energy``,
#: ``categories``, ``ingredients`` and ``products``, and each part has
#: ``name``, ``type`` and ``amount``.
FORCE = """
local function part(name, amount)
  return {name = name, type = "item", amount = amount}
end

local recipes = {}
for i = 1, RECIPE_COUNT do
  local name = string.format("recipe-%05d", i)
  recipes[name] = {
    name = name,
    enabled = true,
    hidden = false,
    energy = 0.5,
    categories = {"crafting"},
    ingredients = {part("iron-plate", 1), part("copper-plate", 2)},
    products = {part(name, 1)},
  }
end

-- A technology with the effects the adapter hashes.
local technologies = {}
for i = 1, TECHNOLOGY_COUNT do
  local name = string.format("tech-%04d", i)
  technologies[name] = {
    researched = (i % 2 == 0),
    enabled = true,
    level = 1,
    prototype = {effects = {{type = "unlock-recipe", recipe = "recipe-00001"}}},
  }
end

local force = {name = "player", recipes = recipes, technologies = technologies}

-- The observed 2.1.23 runtime context.
local surface = {name = "nauvis"}
local p = {force = force, surface = surface}
local c = {surface = surface}
local game = {tick = 1000}
local script = {active_mods = {base = "2.1.23"}}
local defines = {flow_precision_index = {ten_minutes = 60}}
local prototypes = {entity = {}, item = {}, recipe = {}}

local function encode(value)
  if value == nil then return "null" end
  local kind = type(value)
  if kind == "number" or kind == "boolean" then return tostring(value) end
  if kind == "string" then
    return '"' .. value:gsub('\\\\', '\\\\\\\\'):gsub('"', '\\\\"') .. '"'
  end
  if kind ~= "table" then return "null" end
  local count, is_array = 0, true
  for key in pairs(value) do
    count = count + 1
    if type(key) ~= "number" then is_array = false end
  end
  local parts = {}
  if is_array and count == #value then
    for _, item in ipairs(value) do parts[#parts+1] = encode(item) end
    return "[" .. table.concat(parts, ",") .. "]"
  end
  for key, item in pairs(value) do
    parts[#parts+1] = '"' .. tostring(key) .. '":' .. encode(item)
  end
  return "{" .. table.concat(parts, ",") .. "}"
end
helpers = {json_encode = encode}
"""


def _machine_prototypes(count: int) -> str:
    """Return Lua that builds ``count`` machine prototypes.

    The observed live report has 256 machines, each declaring a crafting
    category, an energy usage, the allowed effects and the allowed module
    categories. The mock raises for an absent member, exactly as the live
    2.1.23 runtime does.
    """
    return f"""
local function prototype(fields)
  return setmetatable({{}}, {{
    __index = function(_, key)
      local value = fields[key]
      if value == nil then
        error("LuaEntityPrototype doesn't contain key " .. tostring(key), 2)
      end
      return value
    end,
  }})
end

local entity = {{}}
for i = 1, {count} do
  local name = string.format("machine-%04d", i)
  entity[name] = prototype({{
    crafting_categories = {{crafting = true}},
    energy_usage = 90000,
    allowed_effects = {{speed = true, productivity = true}},
    allowed_module_categories = {{speed = true}},
    fluidbox_prototypes = {{}},
    module_inventory_size = 2,
    get_crafting_speed = function() return 0.75 end,
    type = "assembling-machine",
    name = name,
  }})
end
prototypes.entity = entity
"""


def _run_once(lua_module, program: str) -> float:
    """Execute one program and return its elapsed wall time in seconds."""
    runtime = lua_module.LuaRuntime(unpack_returned_tuples=True)
    started = time.perf_counter()
    runtime.execute(program)
    return time.perf_counter() - started


def measure(recipe_count: int, machine_count: int, repeats: int,
            *, skip_fingerprint: bool = False, fast_path: bool = False
            ) -> dict[str, Any]:
    """Measure the per-poll Lua cost at the given catalog size.

    With ``skip_fingerprint`` the per-recipe and per-technology fingerprint
    hashing is disabled, which isolates how much of the poll cost is the
    fingerprint rather than the bounded page read itself.

    With ``fast_path`` the recipe adapter is omitted entirely, which is
    what the backend's ``noCatalog`` view does.
    """
    try:
        import lupa
    except ImportError:  # pragma: no cover - depends on the environment
        return {"status": "BLOCKED", "reason": "lupa is not installed"}

    lua = _adapter_lua()
    prelude = (
        f"RECIPE_COUNT = {recipe_count}\n"
        f"TECHNOLOGY_COUNT = 64\n"
        + FORCE
        + _machine_prototypes(machine_count)
    )
    if fast_path:
        # This is exactly what the backend's noCatalog view substitutes for
        # the adapter placeholder.
        program = prelude + "\nlocal PAGE = 1\nlocal capabilities=nil local catalog_status=nil\n"
    else:
        program = prelude + "\nlocal PAGE = 1\n" + lua + "\n"
    if skip_fingerprint:
        # The fingerprint hashes every recipe's ingredients and products.
        # Replacing the hash function with a no-op isolates that cost
        # without touching the shipped adapter source.
        program = program.replace(
            "local function hash_text(text)",
            "local function hash_text(text) if true then return end",
            1,
        )

    # One warm-up run so the measurement is not dominated by first-call
    # Lua table allocation.
    _run_once(lupa, program)

    samples: list[float] = []
    for _ in range(repeats):
        samples.append(_run_once(lupa, program))
    return {
        "status": "ok",
        "recipe_count": recipe_count,
        "machine_count": machine_count,
        "repeats": repeats,
        "fingerprint": not skip_fingerprint,
        "catalog_adapter": not fast_path,
        "seconds_min": round(min(samples), 6),
        "seconds_median": round(statistics.median(samples), 6),
        "seconds_mean": round(statistics.fmean(samples), 6),
        "seconds_max": round(max(samples), 6),
    }


def main() -> int:
    repeats = 5
    results = []
    for recipes, machines, label in (
        (OBSERVED_RECIPE_COUNT, OBSERVED_MACHINE_COUNT, "observed live scale"),
        (1000, 256, "small catalog"),
        (100, 32, "tiny catalog"),
    ):
        measurement = measure(recipes, machines, repeats)
        if measurement.get("status") == "ok":
            measurement["label"] = label
            # The 1-second poll runs this 60 times a minute.
            median = measurement["seconds_median"]
            measurement["cpu_seconds_per_minute_at_1s_poll"] = round(
                median * 60.0, 4)
            measurement["polls_per_minute"] = 60
        results.append(measurement)
        print(json.dumps(measurement, sort_keys=True), flush=True)

    # Isolate the fingerprint cost at the observed live scale.
    without = measure(OBSERVED_RECIPE_COUNT, OBSERVED_MACHINE_COUNT, repeats,
                      skip_fingerprint=True)
    if without.get("status") == "ok":
        without["label"] = "observed live scale, fingerprint disabled"
        without["cpu_seconds_per_minute_at_1s_poll"] = round(
            without["seconds_median"] * 60.0, 4)
        results.append(without)
        print(json.dumps(without, sort_keys=True), flush=True)

    # The fast path: the recipe adapter is omitted entirely.
    fast = measure(OBSERVED_RECIPE_COUNT, OBSERVED_MACHINE_COUNT, repeats,
                   fast_path=True)
    if fast.get("status") == "ok":
        fast["label"] = "observed live scale, catalog adapter omitted"
        fast["cpu_seconds_per_minute_at_1s_poll"] = round(
            fast["seconds_median"] * 60.0, 4)
        results.append(fast)
        print(json.dumps(fast, sort_keys=True), flush=True)

        full = next((r for r in results
                     if r.get("label") == "observed live scale"), None)
        if full is not None:
            summary = {
                "status": "ok",
                "label": "fast path versus the full catalog read",
                "full_median_seconds": full["seconds_median"],
                "fast_median_seconds": fast["seconds_median"],
                "speedup_x": round(
                    full["seconds_median"] / fast["seconds_median"], 2)
                if fast["seconds_median"] > 0 else None,
                "full_cpu_seconds_per_minute_at_1s_poll": round(
                    full["seconds_median"] * 60.0, 4),
                "fast_cpu_seconds_per_minute_at_1s_poll": round(
                    fast["seconds_median"] * 60.0, 4),
            }
            print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
