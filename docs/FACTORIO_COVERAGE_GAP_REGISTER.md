# Missing, under-specified or unverified Factorio coverage: work queue for Zoo Code

Updated 2026-10-18. Read with [complete R01-R20 index](../ROADMAP.md), [mechanics hub](FACTORIO_MECHANICS_REFERENCE.md), [scripting API hub](FACTORIO_SCRIPTING_API_REFERENCE.md), [base + expansion quirks](FACTORIO_QUIRKS_AND_EDGE_CASES.md) and [acceptance contract](PLANNING_REQUIREMENTS.md).

**Why this exists:** a feature mentioned in a roadmap does not mean the AI understands it, has seen it, or is capable of executing it. This list names plausible gaps from a broad source/API comparison. It is **not** an allegation that the corresponding source has a bug, or that the feature is unsupported in the game. Each entry starts with **Open / needs evidence** unless an exact fixture proves it. R20 mods are deferred until vanilla + first-party expansion acceptance.

**Provenance:** https://wiki.factorio.com/ ; https://lua-api.factorio.com/latest/ ; https://factorio.com/blog/ . For an exact mechanic, look up the matching versioned class, prototype and game-observed fields first.

## Base game: deeper coverage beyond the current B01-B33 catalog

| Gap | R ID(s) | Missing or frequently overlooked behavior to model and test |
|---|---|---|
| G-B01 | R04/R18 | Freeplay settings, difficulty/achievement eligibility, map generation seeds, custom scenarios vs normal achievements |
| G-B02 | R04/R05 | Map chunk lifecycle, force-specific charted/fog knowledge, radars, remote map view, chart-tag ownership |
| G-B03 | R04/R05/R18 | Multiplayer: force alliances, player permissions, owner/observer, separate inventory/controllers, reconnect and lag |
| G-B04 | R05/R18 | Player crafting queue, cancel/refund, build reach, mining reach, equipment swap, cursor ghost and inventory filters |
| G-B05 | R05/R14 | Death/respawn, corpse/item retrieval, inventory/belongings ownership and save-specific settings |
| G-B06 | R04/R06 | Factoriopedia/unlocks, hidden/disabled recipe vs nonexistent prototype; recipes with empty inputs, multiple outputs, catalysts |
| G-B07 | R06 | Productivity boundaries, beacons and module incompatibilities, furnace auto recipe selection, speed caps and power factors |
| G-B08 | R06/R13 | Chemical processing and oil cracking: refinery input/output ordering, fluid temperatures, tank backpressure, balanced cracking |
| G-B09 | R06/R13 | Steam engines/turbines, boilers/reactors, nuclear fuel cells, heat exchangers, emergency power/islanding and reserve time |
| G-B10 | R06/R08 | Inserter circuit read-hand/filters/stack overrides, stack/research, angles, near/far drop, bulk insertion and throughput |
| G-B11 | R06/R08 | Splitters priority/filter, belt side loading, compression, express versus slower belts, underground span, pipes crossover |
| G-B12 | R06/R13 | Miner drill geometry/patch overlap, fluid mining, uranium acid, resource richness/productivity and patch lifetime |
| G-B13 | R06/R08 | Item fuel values, burner heat, electric versus burner machines, alternative fuels, equipment-grid power |
| G-B14 | R06/R08 | Loaders and special prototype-controlled belt stacking/interaction; not necessarily present in vanilla active recipes |
| G-B15 | R07/R08 | Blueprint books nested, snapping/alignment, circuit wires, schedules, parameter substitutions, icons, unknown fields and versions |
| G-B16 | R07/R08 | Upgrade planner / deconstruction / copy-paste / quickbar and undo ownership, cancel actions without demolishing protected builds |
| G-B17 | R08/R09 | Real building prerequisites: researched entity, surface, hand/robot reach, tiles, cliffs, underground/pipe wiring and occupancy |
| G-B18 | R08/R09 | Robot-driven ghost expiration, landfill and foundation dependency order, partial construction and refused upgrade |
| G-B19 | R10 | Advanced combinator math/bitwise/selector priority, signal quality, wildcard signals, per-tick latency, zero vs absent |
| G-B20 | R10 | Latches/hysteresis, memory cells, feedback oscillation, rising/falling edges, power-loss restart and circuit-network identity |
| G-B21 | R11 | Train wagon filters, stack size, platform length, loading/inserter/belt constraints, fluid wagons and pumps |
| G-B22 | R11 | Rail block/chain signal reservation, curves, bidirectional pathfinding, train splitting, re-routing and no-path recovery |
| G-B23 | R11 | Station limits/priorities, disabled stops, refueling interrupts, wait conditions, deadlock/congestion and throughput realism |
| G-B24 | R12 | Distinguish logistic storage/requester/provider/buffer/active-passive roles, trash, priority, robots in flight and queues |
| G-B25 | R12 | Personal roboports vs static networks, robot network splits, charging and energy starvation, repair/resupply |
| G-B26 | R13 | Machine priority under brownout, inventory starvation, overflow/byproducts, pollution/alerts and evolving shortages |
| G-B27 | R13 | Electricity graphs, production statistics sampling and actual 1/5/10-minute throughput variance |
| G-B28 | R14 | Enemy types and resistances, tank/car/spidertron fuel/ammo/equipment, artillery range and friendlies |
| G-B29 | R14 | Radar/outpost early threat detection, wall repair, ammo throughput, retreat paths and defensive combat bots |
| G-B30 | R18 | Legitimate rocket launch and victory, science order, achievements restrictions and repeatable beginner/fresh-start tests |
| G-B31 | R18 | Megabase UPS, train path budget, entity update rates, logistics network overload, save/replay and long endurance |
| G-B32 | R17 | In-game GUI accessibility, shortcut controls, multiple players' different UI state, locale strings and custom keybinding conflicts |

## Expansion and separate feature-flag gaps

| Gap | R ID(s) | Missing or frequently overlooked behavior to model and test |
|---|---|---|
| G-S01 | R04/R06 | First-party feature/dependency inventory: Space Age, Elevated Rails, Recycler, Quality and enabled-mod ordering |
| G-S02 | R15 | Rocket silo/rocket-part cost, cargo landing pads, interplanetary logistics and surface-dependent launch limits |
| G-S03 | R15 | Stationary versus moving platform operation, hub inventory, orbital requests, dropping unwanted items and cargo loss |
| G-S04 | R15 | Space-platform shape, thruster boundary geometry, asteroid harvest/fragmentation/reprocessing and ammo autonomy |
| G-S05 | R15 | Distinct route fuel/oxidizer requirements, asteroid damage, circuit/platform schedule interrupts and safe return |
| G-S06 | R06/R13 | Vulcanus molten iron/copper/stone byproducts, calcite, tungsten, lava pump/connection and blocked casting |
| G-S07 | R08/R14 | Vulcanus demolishers, disputed territory, mining/build hazards and researched/approved responses |
| G-S08 | R06/R13 | Fulgora scrap multi-products and recycler feedback, excess intermediates, Holmium availability and stack priorities |
| G-S09 | R08/R11 | Fulgora shallow/deep oil ocean island topologies, rail ramps/support foundations and lightning power |
| G-S10 | R06/R13 | Gleba agriculture and soil, seed yield/plant growth, nutrients/biochambers, spoilage time and humidity |
| G-S11 | R06/R13 | Gleba science lifespan and rocket arrival freshness, inserter-held spoilage, trash loops and stop/restart starvation |
| G-S12 | R14 | Gleba pentapod behaviors, eggs and bioflux/captive-spawner survival, spoilage/hatching, separate research controls |
| G-S13 | R08/R13 | Aquilo ice platforms, terrain restrictions, machine heating adjacency, fusion/cryogenic temperatures |
| G-S14 | R13/R15 | Aquilo off-world replenishment, heating cold start and route delay into loss of all power |
| G-S15 | R16 | Probability/quality distributions, research tiers, recycler output, quality filters and catalyst feedback cycles |
| G-S16 | R16 | Quality-enabled versus Quality-off data profiles; fluids without quality; module probability vs guaranteed output |
| G-S17 | R11 | Elevated Rails curvature, ramp footprint/support spacing and distinct ground/elevated rail signal connectivity |
| G-S18 | R15/R18 | Final Space Age progression and victory, planet prerequisites, edge travel and robust recovery from lost platforms |
| G-S19 | R04/R05 | Expansion-specific API events, runtime prototypes, empty surfaces, hidden recipes, changed prototype schema |
| G-S20 | R18 | Long routes and Gleba/Aquilo logistics over >60 min with spoilage/damage/research shifts; UPS and economy budgets |

## Scripting, AI architecture, public release and mod interoperability gaps

| Gap | R ID(s) | Missing or frequently overlooked behavior to model and test |
|---|---|---|
| G-A01 | R01/R03 | Engine/script control boundaries: model may suggest, but cannot issue arbitrary console, Lua or game-state modifications |
| G-A02 | R01/R17 | Custom-input event ordering, rebound controls, manual takeover during model output, multi-player authority |
| G-A03 | R02/R19 | Safe RCON configuration, loopback-only servers, reconnect auth, error/reply handling, command authorization |
| G-A04 | R03/R20 | Mod settings/data/control lifecycle, mod API migrations, storage schema and object validity |
| G-A05 | R04/R05 | Snapshot cache invalidation on prototype/research/force/surface/quality changes |
| G-A06 | R05/R18 | Matrix may say 'has evidence' even if the evidence indicates failure; separate successful outcomes and verification |
| G-A07 | R17 | GUI script state and per-player identity; stale callbacks, on_load recovery and localized text |
| G-A08 | R18 | Tick load, event filters, explicit time budgets, game pause/tick-rate effects on predicted throughput |
| G-A09 | R18/R20 | Multiplayer save/load consistency and deterministic Lua event registration; no unsynchronized wall-clock/IO assumptions |
| G-A10 | R19 | Pin API versions, engine builds, scripts/dependencies licenses and provenance; reproducible builds and restore |
| G-A11 | R19 | Accessibility, keyboard/game controller handling, localization and setup diagnostics |
| G-A12 | R19 | Network disruptions, service crashes, GPU VRAM pressure, supported remote/cloud security and resource budgets |
| G-A13 | R20 | Mod conflicts, optional/mandatory dependencies, changed prototype names and missing research/quality definitions |
| G-A14 | R20 | RCON/script access conflicts with mods, remote interfaces absent, mod-specific registered tools/protocols |
| G-A15 | R20 | Space Exploration hull/integrity/stress, alternate rocket/ship cargo systems and mod-specific equipment/energy/defense |
| G-A16 | R20 | Krastorio 2, Industrial Revolution, Exotic Industries, Angels/Bob's, Py and other overhaul candidates are **research-only** until selected and independently version-validated |
| G-A17 | R20 | LTN/Cybersyn station adapters and Recursive Blueprints+ must follow their mod APIs and permissions; no assumption of built-in behavior |
| G-A18 | R18/R19 | Telemetry provenance and display: observed versus estimated, stale snapshots, version/fingerprint and capability confidence |

## How Zoo closes gaps

For any current R task: (1) select only relevant G-B/G-S/G-A items; (2) find exact current engine docs, prototype schema, YouTube candidate if useful, and legitimate preconditions; (3) add offline positive/negative fixtures; (4) request human approval before live game testing; (5) record expected-versus-observed evidence in the R05 ledger; (6) update the row's status only for the demonstrated profile/version and surface. **Do not treat a future requirement or online documentation link as a completed feature.**

When new systems or quirky interactions are found in release notes, community guides or videos, add a uniquely identified row with a source/URL, date, version, confirmed behavior (or hypothesis), and reproducer. Include *regular Factorio* cases as well as Space Age. Keep the last phase modded: optional compatibility profiles, not an excuse to disable safety or assume shared recipes.
