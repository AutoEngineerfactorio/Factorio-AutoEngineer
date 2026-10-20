# Factorio Lua reference workflow for Zoo Code

Use this alongside `01-project.md` and `../docs/FACTORIO_SCRIPTING_API_REFERENCE.md`. The existing scripting guide is the primary detailed project reference; **do not replace it with generic Lua documentation**.

## Before writing any Factorio Lua
1. Determine the actual Factorio executable/test profile version and enabled mods; do not assume latest docs match the running game.
2. Select the exact official API version:
   - Stable 2.0.77: https://lua-api.factorio.com/2.0.77/
   - Experimental 2.1.22: https://lua-api.factorio.com/2.1.22/
   - Version list: https://lua-api.factorio.com/
3. Read the relevant official page for each method, prototype, field, and event. The latest URL is useful for discovery, **not authoritative for another installed version**.
4. Consult `docs/FACTORIO_SCRIPTING_API_REFERENCE.md`, `docs/FACTORIO_MECHANICS_REFERENCE.md`, `docs/FACTORIO_QUIRKS_AND_EDGE_CASES.md`, and `docs/CONTINUOUS_MOD_BENCHMARKS.md` for AutoEngineer requirements.

## Official primary reference map
- Runtime Lua API (control stage): https://lua-api.factorio.com/2.1.22/index-runtime.html
- Prototypes (data stage): https://lua-api.factorio.com/2.1.22/index-prototype.html
- Mod lifecycle: https://lua-api.factorio.com/2.1.22/auxiliary/data-lifecycle.html
- Storage/save/load: https://lua-api.factorio.com/2.1.22/auxiliary/storage.html
- Structure and dependencies: https://lua-api.factorio.com/2.1.22/auxiliary/mod-structure.html
- Auxiliary topics, migrations and JSON schema: https://lua-api.factorio.com/2.1.22/index-auxiliary.html
- Tutorials: https://wiki.factorio.com/Tutorial:Modding_tutorial
- General Lua 5.2 language manual (syntax only; Factorio APIs differ): https://www.lua.org/manual/5.2/

If running Factorio 2.0.77, **replace /2.1.22/ with /2.0.77/** in these official API URLs and verify a matching page exists.

## AutoEngineer implementation priorities
- **Telemetry first:** read-only entity, inventory, fluid, power, logistic-network, circuit-network, train, research, surface, platform and quality observations where supported by the pinned API.
- **AI Helper:** plan using *observed live prototypes and recipes*, not hardcoded vanilla assumptions; handle unlocks, alternate recipes, byproducts, catalyst loops, fluid temperature and productivity constraints.
- **Blueprint help:** use legal blueprint/string and entity/recipe interfaces; avoid direct arbitrary execution or freeform RCON, and require explicit approval for world-changing commands.
- **Mod compatibility:** Space Age, Space Exploration, and Pyanodons are distinct environments; keep pY continuously benchmarked in its own isolated profile. Never assume all prototypes exist.
- **Efficiency and safety:** avoid full scans every tick, use event-driven/delta collection, bound loops and payload sizes, preserve multiplayer determinism, validate object existence and lifecycle.
- **Tests:** inspect exact files -> propose bounded changes -> run syntax/static tests -> test disposable saves -> verify live state, performance and permissions. Do not claim live compatibility from a static test.

When Zoo cannot access a URL, report that limitation and use the locally checked-in reference index; **do not invent API signatures**. Documentation research alone is not authorization to execute Lua, grant tool approvals, or modify gameplay.
