# Factorio 2.x Lua scripting and mod architecture: authoritative reference for Zoo Code

Updated 2026-10-20. Related: [Factorio mechanics](FACTORIO_MECHANICS_REFERENCE.md), [quirk tests](FACTORIO_QUIRKS_AND_EDGE_CASES.md), [coverage gap register](FACTORIO_COVERAGE_GAP_REGISTER.md), [R01-R20 roadmap](../ROADMAP.md), [offline API archive](OFFLINE_FACTORIO_API.md). **This document indexes the complete official API**, rather than trying to paste thousands of potentially stale method signatures into a file. Read the precise versioned class/property documentation when writing code.

**Supported API version: 2.1.23.** The offline archive at `.local/factorio-api-offline/2.1.23/files/` is a verbatim copy of the verified 2.1.23 installation's `doc-html`; its `runtime-api.json` and `prototype-api.json` declare `application_version` `2.1.23` and `api_version` `6`. The archived 2.1.22 and 2.0.77 folders are historical comparison material only and must not be used as the active API contract. Official online pages are pinned to `/2.1.23/` below; `/latest/` is useful for discovery but is **not** authoritative for the installed version.

## Canonical complete API indexes (not an abridged list)

| Domain | Complete upstream reference | How to use it |
|---|---|---|
| Overview and language | https://lua-api.factorio.com/2.1.23/index.html | Modified Lua 5.2; mod lifecycle and API version |
| Runtime classes, methods, properties | https://lua-api.factorio.com/2.1.23/index-runtime.html and https://lua-api.factorio.com/2.1.23/classes.html | Check exact read/write attributes, nilability, versions and validity |
| Every documented event and event structure | https://lua-api.factorio.com/2.1.23/events.html | Use specified event payloads; never guess an event field |
| Runtime concepts / input types | https://lua-api.factorio.com/2.1.23/concepts.html | Exact type/data shapes, inventories, fluids, quality, positions |
| Runtime enums/defines | https://lua-api.factorio.com/2.1.23/index-auxiliary.html | Constants for controllers, commands, direction, rail and signal semantics |
| Complete prototype definitions and types | https://lua-api.factorio.com/2.1.23/index-prototype.html | Data-stage items, recipes, machines, entity behavior, surface/mapgen and planet specs |
| Settings and file structures | https://lua-api.factorio.com/2.1.23/auxiliary/mod-structure.html and https://wiki.factorio.com/Tutorial:Mod_settings | Dependency order, settings/prototype/runtime stages |
| Mod load/upgrade sequence | https://lua-api.factorio.com/2.1.23/auxiliary/data-lifecycle.html | on_init/on_load/on_configuration_changed and stages |
| Persistent state | https://lua-api.factorio.com/2.1.23/auxiliary/storage.html | save/load-safe storage and LuaObjects |
| Migrations | https://lua-api.factorio.com/2.1.23/auxiliary/migrations.html | JSON renames, Lua conversions and version compatibility |
| Machine-readable documentation | https://lua-api.factorio.com/2.1.23/auxiliary/json-docs-runtime.html and https://lua-api.factorio.com/2.1.23/index-auxiliary.html | Tooling/codegen can read upstream JSON schema; pin version and document generation, don't assume latest matches local |
| Intro/tutorial | https://wiki.factorio.com/Tutorial:Modding_tutorial/Gangsir | Real project examples, locale and prototypes |
| Console versus mod script | https://wiki.factorio.com/console | Ad hoc /c scripts are NOT the normal authorized agent action path |
| Debugging, profiler and auxiliaries | https://lua-api.factorio.com/2.1.23/index-auxiliary.html | Instrument mode, libraries, prototype inheritance, noise expressions, other advanced topics |

**Version contract:** bind API references to the installed executable's version + mod/expansion fingerprints. On upgrade, compare removed/renamed events, prototype flags, and fields. The `/latest/` endpoint evolves; store versioned evidence without silently auto-upgrading integration. Code generation cannot infer permissions from an API signature.

**Exact-signature check before editing Lua:** before changing any Lua source, confirm the exact 2.1.23 signature of every API call the change touches, by grepping `.local/factorio-api-offline/2.1.23/files/runtime-api.json` or `prototype-api.json` for the class, method, property or event and reading its `parameters` and `type`. A name absent from the 2.1.23 JSON is **unverified**: report it as missing documentation instead of guessing, and never substitute a 2.1.22, 2.0.77 or `/latest/` signature. Cite the archive file and exact API name in the change report.

`agent/factorio_api_2123.py` performs this lookup programmatically and fails closed on an unknown name; see [docs/FACTORIO_API_INDEX_2123.md](FACTORIO_API_INDEX_2123.md). Lua Language Server diagnostics against the exact 2.1.23 API are documented in [docs/LUA_DIAGNOSTICS_2123.md](LUA_DIAGNOSTICS_2123.md).

## The three scripting stages and their contracts

| Stage | Standard files / entry points | Allowed purpose | Frequent mistakes |
|---|---|---|---|
| **Settings** | `settings.lua`, `settings-updates.lua`, `settings-final-fixes.lua` | Define mod settings prototypes and settings compatibility | Assuming runtime settings are static, changing startup settings without restart, conditional require causing multiplayer CRC divergence |
| **Data/prototype** | `data.lua`, `data-updates.lua`, `data-final-fixes.lua`; optional `prototypes/` modules | Define recipes, technologies, items, entities, GUI styles, tile/platform/quality features, custom inputs and build capability | Mutating prototype `data.raw` as if it were a live inventory, wrong ordering/dependency or cloned prototype and missing fields |
| **Runtime/control** | `control.lua` plus required Lua modules | Event handlers, legitimate read-only observation, mod GUI, state tracking and specifically authorized in-game effects | Running gameplay actions while a module is loaded, stale LuaObjects, save/load desync, heavy per-tick enumeration |

Factorio loads settings, data and runtime separately. Mandatory `info.json` defines name/version/dependencies/factorio_version; `locale/`, `migrations/`, `scenarios/`, `campaigns/`, `tutorials/` and assets have their own special handling. **Space Age**, **Quality**, **Elevated Rails** and **Recycler** are distinct first-party mods/features with dependency constraints; inspect actual `mods` and feature flags. Do not hardwire all expansions on or confuse modded Space Exploration with Space Age.

### Initialization, save/load and migrations: very important

- `script.on_init()`: initialize new mod state and persistent tables. New mods added to a save also use initialization.
- `script.on_load()`: restore *local function references/conditional handler registrations/metatables only*. Do not read `game` or mutate `storage`; violations can cause multiplayer desyncs. `storage` (formerly `global` before 2.0) is not fully ready at the initial `control.lua` evaluation.
- `script.on_configuration_changed()`: adapt valid persistent state when mods/versions/startup settings/prototypes change. Don't rebuild unrelated user data without migration review.
- JSON and Lua migrations have defined application ordering. Prototype renames/types may invalidate LuaObject pointers; validate `.valid` and rebuild indices. Ghosts may disappear after migrations.
- Persistent `storage` supports serializable primitives, tables and allowed LuaObject references; do not store closures/functions, file handles, unregistered metatables, or transient event payloads.
- In multiplayer, joining peers load the save with previously applied migrations; conditional event registration must be the same for every participant. Server authority, anti-desync and deterministic ordering take priority.

## Runtime API systems: coverage map for R milestones

| Runtime/API subsystem | Typical objects / docs | R milestones | Required tricky cases |
|---|---|---|---|
| Event registration, filters, on_nth_tick, custom events | `LuaBootstrap`, `defines.events` | All | Only one handler per mod/event, second registration replaces first; namespace event dispatch; tick cost |
| Settings & configuration | `settings`, runtime change events | R04/R19/R20 | Per-player vs startup/global changes; handle disabled mod and stale cached config |
| Player state, permissions, force/technology | `LuaPlayer`, `LuaForce`, `LuaPermissionGroup` | R01/R04/R05/R17 | Nil player/character, controller changes, multiple forces, research edits invalidate plans |
| Surfaces, tiles, pollution, fog/visibility | `LuaSurface`, `LuaTile`, `LuaPlanet` | R04/R08/R13/R15 | Chart rights vs generated chunks; deleted surface; planet surface not necessarily created |
| Entities, quality, direction, equipment | `LuaEntity`, prototype classes, inventory, fluidbox | R05/R06/R08/R16 | Expired `LuaEntity.valid`, multiple inventory roles, filters, quality item identifiers |
| Recipe/prototype queries | `LuaRecipePrototype`, `LuaTechnologyPrototype`, `LuaEntityPrototype` | R04/R06/R20 | Actual registered prototypes, disabled/unresearched recipe vs absent prototype, mod diffs |
| Trains and rails | `LuaTrain`, `LuaSchedule`, `LuaRailPath`, signals | R11 | Train split/merge invalidates IDs and refs; schedule interrupt/limit changes |
| Robots, logistics and electric networks | roboport/entity/equipment/logistic sections | R12/R13 | Coverage topology, power, charging queues, independent bot jobs and inventory |
| Circuits and control behavior | `LuaControlBehavior`, combinator/wire/signal interfaces | R10 | Red/green wiring, network IDs, wire changes, combinator tick lag |
| Construction, plans and ghosts | `LuaSurface`, `LuaEntity`, planners, `LuaItemStack` | R07/R08/R09 | Explicit build permission, supply, ghost != physical entity; script-creation is NOT legal game construction |
| GUI, rich texts and feedback | `LuaGui`, `LuaGuiElement`, `rendering` | R17 | Per-player UI lifecycle, stale GUI elements, callbacks/tag validation, closing/disconnect |
| Event logs and diagnostics | `game`, `script`, Profiler; instrumentation | R03/R18 | Bounded telemetry, no heavy on_tick work, no raw secrets in logs |
| Custom inputs + takeover | `CustomInputPrototype`, custom-input events | R01/R17 | Key binding collisions, input rebound, driving/controller/death/surface changes |
| Cross-mod integration | `LuaRemote`, remote interfaces | R01/R20 | Missing interface/function, dependency load order, namespacing, no assumed trust |
| Console/RCON and commands | `LuaCommandProcessor`, `commands` | R02/R19 | Public console is not action authorization; dangerous /c changes invalidate achievements |
| Space platforms, travel and cargo | `LuaSpacePlatform`, `LuaPlanet`, `LuaSpaceConnection` | R15 | Missing hub/surface, platform state/route changes, wait conditions, asteroid hazards |
| Crafting, spoilage and quality | item stacks, recipes, quality prototypes | R06/R13/R16 | Freshness/tick timing, fluid quality exception, probabilistic output, planet eligibility |
| Multiplayer, replay and scenarios | player connect/disconnect, mod state/permissions, scenario scripts | R17/R18/R20 | Same event registration across peers, late commands, host/client desync and replay |
| Performance, map generation, noise, localization | auxiliary docs and prototype tree | R18/R19/R20 | Entity counts, chunk generation budgets, string translation callback, base-game language |

Useful exact API pages:
- `script` lifecycle/events: https://lua-api.factorio.com/2.1.23/classes/LuaBootstrap.html
- `remote` interfaces: https://lua-api.factorio.com/2.1.23/classes/LuaRemote.html
- `commands`: https://lua-api.factorio.com/2.1.23/classes/LuaCommandProcessor.html
- GUI roots/elements: https://lua-api.factorio.com/2.1.23/classes/LuaGui.html and https://lua-api.factorio.com/2.1.23/classes/LuaGuiElement.html
- Surface and planets: https://lua-api.factorio.com/2.1.23/classes/LuaSurface.html and https://lua-api.factorio.com/2.1.23/classes/LuaPlanet.html
- Platforms: https://lua-api.factorio.com/2.1.23/classes/LuaSpacePlatform.html
- Events with first-party expansion additions: https://lua-api.factorio.com/2.1.23/events.html

## Event families to search by ID in the official events index

- **Players:** created/joined/left/respawned/died/controller changed/driving changed/surface changed/cursor changed/selected entity/custom inputs.
- **Entities:** mined/built/repaired/died/damaged/upgraded/deconstructed/cloned/rotated/teleported/renamed and script-raised counterparts. Entity creation by script may not raise the same events as character, robot or platform construction.
- **Inventories/crafting:** player-craft, on_recipe_crafted, item pickup/dropped/trash/quality, recipe change, fuel and item lifecycle.
- **Logistics/robots:** robot build/mine/charge, ghost/deconstruction, network and coverage changes.
- **Research/force:** technology researched/reset, force created/merged and settings changes.
- **Rail/circuit:** train created/state/schedule changed, rail/entity state changes, output signal reads.
- **Surfaces and chart:** surface created/deleted/renamed/imported, chunk generated/charted, sectors scanned.
- **Space Age:** space platform construction/mining/tiles/state, rocket/cargo, agricultural tower plant/harvest, spoilage, quality changes when present.
- **Multiplayer/UI:** connection/disconnection, permission change, GUI click/selection/value/text and translation-result callback.
- **Performance:** `on_tick`, `on_nth_tick`, event filters, custom event subscriptions and object destroyed callbacks.

**Do not invent event names from these families.** Find exact names and payloads in https://lua-api.factorio.com/2.1.23/events.html, and check whether the installed game version supplies them.

## Safe Lua patterns (illustrative, not an unrestricted agent command API)

Event dispatcher: register each event **once per mod**, then invoke relevant handlers from that dispatcher. Register in `control.lua` or lawful lifecycle steps; don't register the same event twice and silently overwrite an earlier listener.

```lua
-- Minimal read-only observation example for an authorized mod event:
script.on_event(defines.events.on_player_changed_surface, function(event)
    local player = game.get_player(event.player_index)
    if not player or not player.valid then return end
    -- Gather bounded, permission-appropriate observations only.
    -- Do not grant permissions, spawn entities or issue player orders here.
end)

script.on_init(function()
    storage.autoengineer = {schema_version = 1, observations = {}}
end)
```

For approved diagnostic records, capture a bounded snapshot `{tick, game_version, profile_hash, surface_index, force_name, observed_fields, source}`; emit only permitted values, with freshness and chart constraints. Do not serialize entire world data, secret settings or other players' private state.

## Integrating Lua with Python, C# MCP and the desktop AI safely

The AutoEngineer architecture has a restricted C#/Factorio backend, Python observer/planner, and local model. Zoo can **read** Lua/API documentation, **write/review** mod source with permission, and **test** source with offline fixtures. That does not mean the language model may evaluate arbitrary Lua in the game.

- Public API methods include world-editing, teleportation, spawning, force/prototype/technology changes, so exposing Lua/RCON command strings to a goal-seeking model would bypass normal gameplay and current safety policy.
- Use **predefined typed tool names**, validated argument schemas, allowed mode/force/surface/research ranges, narrow player/surface permissions, fresh human approval, one-shot permits, checkpoint and outcome verification.
- Keep Python planning separate from Lua mod functions: only a restricted trusted backend may translate approved intents into legitimate gameplay interfaces. The AI cannot create its own tools/permissions/commands at runtime.
- A dedicated sandboxed test fixture could be used later for **developer QA only** after separate approval; results must be labeled simulated, not legitimate gameplay evidence.
- Mod update/migration or script re-registration may reset/destroy handles; preserve crash-safe job IDs, refuse stale references and reobserve before retry.
- RCON and console commands that run arbitrary scripts can change game state and disable achievements. Never use them as a shortcut around player reach, robots, crafting times, research, save integrity or authorization.

## Scripting test matrix, to expand in a future milestone

| Case | Expected verification |
|---|---|
| LUA-01 initialization | New save loads state once; adding mod to old save initializes without duplicating structures |
| LUA-02 on_load | Read-only storage + handler/metatable restoration; no game read/write or desync |
| LUA-03 migrations | JSON rename & Lua migration order; stale LuaObject.valid and ghost/research changes |
| LUA-04 event dispatch | Two modules listen to same event through one dispatcher; no overwritten callbacks |
| LUA-05 version mismatch | Unsupported runtime/prototype feature is unavailable, not guessed |
| LUA-06 settings | Startup vs runtime vs per-user setting and live change invalidate cached decisions |
| LUA-07 input ownership | Custom-input events revoke AI permits; missing/rebound input safely handled |
| LUA-08 remote interface | Missing, renamed or unauthorized remote function is rejected |
| LUA-09 stale references | Player/force/surface/entity/GUI handle invalidated by death/removal/recreation |
| LUA-10 multiplayer | Join/leave, host restart, deterministic event order and save sync |
| LUA-11 rendering/GUI | Per-player UI clean-up; no ghost controls or duplicate listeners |
| LUA-12 events | Player/robot/platform/script built event semantics are not interchangeable |
| LUA-13 performance | on_tick filters/throttle; no long-running loops and bounded snapshot budget |
| LUA-14 permissions | Helper cannot write; stale permit/tool arguments cannot enter backend |
| LUA-15 telemetry privacy | No secrets/save content or uncharted player data in logs |
| LUA-16 expansion disabled | Feature-gated APIs fail closed with first-party component off |
| LUA-17 platform | Missing hub/planet/surface, cargo state and schedule changes do not imply successful voyage |
| LUA-18 recipes | Surface/research/quality and module legality checked against current prototypes |
| LUA-19 cross-mod | Optional dependencies, missing remote methods, migrations and namespace collisions |
| LUA-20 public packaging | No Lua snippets that auto-execute outside approved mod lifecycle, no private saves/assets shipped |

All LUA cases are **planned**, not passed. Give each the same profile/version/source/expected/observed/run evidence required by R05.
