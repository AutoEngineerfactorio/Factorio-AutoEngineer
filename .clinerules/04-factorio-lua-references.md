# Factorio Lua reference workflow for Zoo Code

Use this alongside `01-project.md` and `../docs/FACTORIO_SCRIPTING_API_REFERENCE.md`. The existing scripting guide is the primary detailed project reference; **do not replace it with generic Lua documentation**.

## Before writing any Factorio Lua
1. Determine the actual Factorio executable/test profile version and enabled mods; do not assume latest docs match the running game.
2. Use the **exact offline 2.1.23 archive** at `.local/factorio-api-offline/2.1.23/files/`:
   - `runtime-api.json` (runtime/control stage) and `prototype-api.json` (data stage) for exact signatures.
   - `index.html` and the per-class HTML pages for readable documentation.
   - Both JSON files declare `application_version` `2.1.23` and `api_version` `6`.
   - The archived `2.1.22` and `2.0.77` folders are historical comparison material only, never the active contract.
3. Read the relevant official page for each method, prototype, field, and event. The latest URL is useful for discovery, **not authoritative for another installed version**.
4. Consult `docs/FACTORIO_SCRIPTING_API_REFERENCE.md`, `docs/FACTORIO_MECHANICS_REFERENCE.md`, `docs/FACTORIO_QUIRKS_AND_EDGE_CASES.md`, and `docs/CONTINUOUS_MOD_BENCHMARKS.md` for AutoEngineer requirements.

## Exact-signature check before editing Lua
Before modifying any Lua source, confirm the exact 2.1.23 signature of every API call the change touches:
1. Grep `.local/factorio-api-offline/2.1.23/files/runtime-api.json` or `prototype-api.json` for the exact class, method, property or event name.
2. Read its `parameters`, `type` and `description` before writing the call.
3. If the name is absent from the 2.1.23 JSON, treat it as **unverified**: report the missing documentation instead of guessing. Never substitute a 2.1.22, 2.0.77 or `/latest/` signature.
4. Cite the archive file and the exact API name in the change report.

## Official primary reference map
Pinned to the supported target 2.1.23:
- Runtime Lua API (control stage): https://lua-api.factorio.com/2.1.23/index-runtime.html
- Prototypes (data stage): https://lua-api.factorio.com/2.1.23/index-prototype.html
- Mod lifecycle: https://lua-api.factorio.com/2.1.23/auxiliary/data-lifecycle.html
- Storage/save/load: https://lua-api.factorio.com/2.1.23/auxiliary/storage.html
- Structure and dependencies: https://lua-api.factorio.com/2.1.23/auxiliary/mod-structure.html
- Auxiliary topics, migrations and JSON schema: https://lua-api.factorio.com/2.1.23/index-auxiliary.html
- Version list: https://lua-api.factorio.com/
- Tutorials: https://wiki.factorio.com/Tutorial:Modding_tutorial
- General Lua 5.2 language manual (syntax only; Factorio APIs differ): https://www.lua.org/manual/5.2/

The archived 2.1.22 and 2.0.77 references remain available under `.local/factorio-api-offline/` for historical comparison only. Do not treat them as the current API.

## AutoEngineer implementation priorities
- **Telemetry first:** read-only entity, inventory, fluid, power, logistic-network, circuit-network, train, research, surface, platform and quality observations where supported by the pinned API.
- **AI Helper:** plan using *observed live prototypes and recipes*, not hardcoded vanilla assumptions; handle unlocks, alternate recipes, byproducts, catalyst loops, fluid temperature and productivity constraints.
- **Blueprint help:** use legal blueprint/string and entity/recipe interfaces; avoid direct arbitrary execution or freeform RCON, and require explicit approval for world-changing commands.
- **Mod compatibility:** Space Age, Space Exploration, and Pyanodons are distinct environments; keep pY continuously benchmarked in its own isolated profile. Never assume all prototypes exist.
- **Efficiency and safety:** avoid full scans every tick, use event-driven/delta collection, bound loops and payload sizes, preserve multiplayer determinism, validate object existence and lifecycle.
- **Tests:** inspect exact files -> propose bounded changes -> run syntax/static tests -> test disposable saves -> verify live state, performance and permissions. Do not claim live compatibility from a static test.

When Zoo cannot access a URL, report that limitation and use the locally checked-in reference index; **do not invent API signatures**. Documentation research alone is not authorization to execute Lua, grant tool approvals, or modify gameplay.
