# Factorio mechanics reference hub for Zoo Code (base game + first-party expansions)

Updated 2026-10-18. Use with [ROADMAP.md](../ROADMAP.md), [R01-R20 acceptance criteria](PLANNING_REQUIREMENTS.md), [Lua scripting/API reference](FACTORIO_SCRIPTING_API_REFERENCE.md), [uncovered systems and gaps](FACTORIO_COVERAGE_GAP_REGISTER.md), and [quirks and regression cases](FACTORIO_QUIRKS_AND_EDGE_CASES.md). This is an **indexed technical reference**, not an offline copy of the whole game manual or a substitute for live game data. Consult the linked sources and relevant runtime/prototype documentation before implementing each mechanic.

## Mandatory evidence and compatibility rules

1. **Know the actual version and content set.** Record Factorio game version/build, enabled Space Age, Quality and Elevated Rails components, enabled third-party mods/settings and their versions, force, research, surface, available prototypes, permissions, charted visibility and observation timestamp/fingerprint. First-party expansion components may be enabled separately; do not assume dependencies based on an old video or version.
2. **Respect source precedence:** authorized current game observations/prototypes (for what is available in this game) > matching-version official runtime/prototype API (what fields mean) > current official Wiki and Wube release notes (behavior) > community tutorials and YouTube (ideas to test). Record contradictions and test rather than inventing data.
3. **Only legitimate game actions.** Read-only introspection permitted by R04, mode policy and chart/fog restrictions is different from spawning, script-assisted building, changing research, teleporting, changing force, or unauthorized RCON/commands. The latter are not authorized gameplay shortcuts.
4. **Profile-aware coverage.** Base Factorio, Space Age, Quality, Elevated Rails, and later third-party mod packs have distinct acceptance records. Research-locks, planet-only recipes and prototype differences remain explicit.
5. **Separate proof levels.** Video/demo -> candidate hypothesis; official written rule -> expected behavior; offline fixture -> code check; authorized, measured disposable-save experiment -> live evidence; endurance -> separately measured acceptance. A green unit suite does not certify game competence.
6. **Agent task contract.** For each R item: cite the applicable source links, list preconditions/unlocks and failure modes, propose a deterministic test, record expected vs observed outcomes, and keep Helper read-only. Human takeover, safe Stop, bounded movement, and locked Full Autonomy always remain.

## Authoritative reference entry points

- **Official Factorio Wiki:** https://wiki.factorio.com/ (mechanics, items, entities, fluids, research, planets, and game-version history)
- **Wube developer news / Friday Facts:** https://factorio.com/blog/ (original rationale and changes; compare final shipped behavior with current game)
- **Official Runtime API:** https://lua-api.factorio.com/latest/index-runtime.html (actual controller types, events, read-only prototype access and restrictions; /latest can change)
- **Official Prototype API:** https://lua-api.factorio.com/latest/index-prototype.html (entities, items, technologies, recipes, surfaces, fluid boxes)
- **Data lifecycle:** https://lua-api.factorio.com/latest/auxiliary/data-lifecycle.html (settings/prototype/runtime stages are distinct; do not use data-stage API as a gameplay action)
- **Major 2.0 changes:** https://wiki.factorio.com/Version_history/2.0.0 and https://factorio.com/blog/post/fff-418
- **Official engine update / content compatibility note:** https://factorio.com/blog/post/fff-442 (notably Quality/Space Age component behavior and fluid revisions).
- **Machine-readable API** is available from the official documentation. Prefer API schemas for typing fields, but cross-check the installed game version.

## Base Factorio systems Zoo must know

| System and R milestone(s) | What to model/observe and never assume | Reference |
|---|---|---|
| Character, force, reach, inventory, health, death and respawn (R01/R05/R18) | Character vs remote-view capabilities, item access, force research, equipment/ammo, death recovery, missing player/vehicle, surface | https://wiki.factorio.com/Controls ; https://lua-api.factorio.com/latest/index-runtime.html |
| Map, charted vs unexplored fog, surfaces and permissions (R04/R05/R08) | Map view does not imply visible entity state or build authority; surface and force matter | https://wiki.factorio.com/Permissions ; https://factorio.com/blog/post/fff-418 |
| Mining, depletion and output (R05/R06/R13) | Resource-drain probability, mining productivity, exhausted patch, blocked output, fluid-dependent mining, different drill types | https://wiki.factorio.com/Mining ; https://wiki.factorio.com/Mining_productivity_%28research%29 |
| Recipes, science, production and module bonuses (R04/R06/R18) | Recipe variants, multiple products, catalyst returns, productivity limits, normal vs researched/planet eligibility, machine speed/energy, stochastic yield | https://wiki.factorio.com/Productivity ; https://wiki.factorio.com/Module ; https://lua-api.factorio.com/latest/index-prototype.html |
| Belts, splitters, undergrounds, lanes and inserters (R06/R08/R13) | Two belt lanes, compression, stacking research, insertion pickup angle and blocked outputs; never treat ideal belt rate as guaranteed | https://wiki.factorio.com/Transport_belts/Physics ; https://wiki.factorio.com/inserters |
| Fluids, pumps, tanks, temperature and thermal networks (R06/R08/R13) | Factorio 2.x fluid segments, finite connections/buffers, pump directions; heat pipes have different thermal behavior; **do not reuse 1.x flow equations** | https://wiki.factorio.com/fluid_system ; https://factorio.com/blog/post/fff-416 ; https://factorio.com/blog/post/fff-442 ; https://wiki.factorio.com/Heat_pipe |
| Electric power, fuel and stored energy (R06/R13) | Generation priority, solar/steam/accumulator response, separate grids, low-power effects, brownout loops | https://wiki.factorio.com/Electric_system |
| Circuit and logistic control (R10) | Red and green signal networks, combinator behavior/latency, wire endpoints, on/off vs read conditions; use current 2.x mechanics | https://wiki.factorio.com/Circuit_network ; https://factorio.com/blog/post/fff-418 |
| Trains, signals, rails, stations and schedules (R11) | Train length/direction, reservations, bidirectional track, chain signals at junctions, signal side, train limits and interrupted schedules | https://wiki.factorio.com/Railway ; https://wiki.factorio.com/Rail_chain_signal ; https://wiki.factorio.com/Tutorial%3ATrain_signals |
| Static and personal logistics/construction robots (R12) | Orange logistics vs green construction area, network connectivity, charge queues, item availability, personal roboport network separation | https://wiki.factorio.com/Logistic_network ; https://wiki.factorio.com/Roboport |
| Blueprints, books, upgrades and deconstruction (R07/R08/R09) | Blueprint string format, books and parameters, entity numbers, wires, mapping, orientation, modded prototypes, ghost vs real entity; library vs in-world behavior | https://wiki.factorio.com/Blueprint_string_format ; https://wiki.factorio.com/Blueprint_library ; https://wiki.factorio.com/Upgrade_planner ; https://wiki.factorio.com/Deconstruction_planner |
| Enemies, damage, turret defenses and pollution (R14/R18) | Enemy evolution != cloud containment; active pollution, different enemy types/resistances, researched ammo, friendly/player danger and repair | https://wiki.factorio.com/Enemies ; https://wiki.factorio.com/Pollution |
| Vehicles/Spidertron and remote control (R05/R14) | Vehicle fuel, equipment, player vs remote access, movement collision, Spidertron straight-line remote order, queue/target loss | https://wiki.factorio.com/Spidertron ; https://wiki.factorio.com/Spidertron_remote |
| Progression and victory (R18) | Different base-vs-Space-Age goals, science availability, unlock prerequisites, observed successful objectives rather than fixtures | https://wiki.factorio.com/Space_Age ; https://wiki.factorio.com/Version_history/2.0.0 |

## Space Age, Quality and Elevated Rails: separate profile features

| Component / surface | Must consider | Authoritative reference |
|---|---|---|
| **Space Age enablement and progression** | Planet discovery and research gates, orbital logistics, shared technologies, distinct victory scenarios; don't assume Quality is enabled merely because Space Age is | https://wiki.factorio.com/Space_Age ; https://factorio.com/blog/post/fff-442 |
| **Nauvis** | Base-world resources, pollution/biters, starter factory, rockets, research, launch logistics and supported surface conditions | https://wiki.factorio.com/Space_Age ; https://wiki.factorio.com/Pollution |
| **Vulcanus** | Lava and molten casting, calcite, tungsten/big-mining-drill requirements, stone byproducts, water alternatives; demolisher territory and combat authorization | https://wiki.factorio.com/Vulcanus ; https://wiki.factorio.com/Lava ; https://wiki.factorio.com/Big_mining_drill |
| **Fulgora** | Scrap recycling, branching outputs and stock disposal, lightning energy/storage, island geometry and elevated rails; deep oil needs a separate rail-support foundation unlock | https://wiki.factorio.com/Oil_ocean ; https://wiki.factorio.com/Recycler ; https://wiki.factorio.com/Rail_support_foundations_%28research%29 |
| **Gleba** | Spoilage even in belts/machines/inserter hands, nutrient fuel loops and agricultural harvest, bioflux, spore pressure, egg freshness and risks | https://wiki.factorio.com/Gleba ; https://wiki.factorio.com/Spoilage_mechanics ; https://wiki.factorio.com/Bio_chamber |
| **Aquilo** | Ice platforms and surface buildability, heated adjacency, freeze thresholds, heat loss under load, cryogenic production and interplanetary resupply | https://wiki.factorio.com/Aquilo ; https://wiki.factorio.com/Heat_pipe |
| **Space platforms** | Connected foundation, edge-only collectors/thrusters, asteroid intake, processing, ammo, engines, electricity, orbital requests, rocket payload/surface origin, cargo drop and route wait conditions | https://wiki.factorio.com/Space_platform |
| **Quality (optional content)** | Item/entity quality identity and corresponding recipe ingredients; fluids have no quality; module chances, speed penalty, researched tiers and recycler loops | https://wiki.factorio.com/Quality ; https://wiki.factorio.com/Quality_module ; https://wiki.factorio.com/Recycler |
| **Elevated Rails (optional content)** | Ramp ground footprint, rail elevations, rail support spacing/collision, deep oil special unlock, power pole/terrain clearance | https://wiki.factorio.com/Rail_ramp ; https://wiki.factorio.com/Rail_support |
| **Late defense/egg systems** | Captive spawner and pentapod eggs, researched upgrades, spoil/starvation and hostile reversion, explicit attack approval | https://wiki.factorio.com/Quality ; https://wiki.factorio.com/Spoilage_mechanics |

## Research and YouTube learning queue (secondary references)

Videos are excellent for spotting *practical* failure modes but cannot certify implementation. Record uploader, video URL, upload date, game version and enabled mods, timestamp, claim, primary-source confirmation and **a separate reproducible test**.

- Nilaus, Gleba farming and spoilage: https://www.youtube.com/watch?v=n3yTCmzb0xE (example designs; validate current spoilage).
- Nilaus, Gleba science handling: https://www.youtube.com/watch?v=YYju-rfgr5k (expiry, throughput, risk).
- Nilaus, Fulgora microfactories: https://www.youtube.com/watch?v=i4Y2JgpLnAs (scrap outputs and constrained layouts).
- Nilaus, Aquilo logistics and science: https://www.youtube.com/watch?v=-71DCrRIwF4 (temperature/transport approaches).
- Rkadindoubt, Factorio circuit-network basics (2026): https://www.youtube.com/watch?v=QK5M_W5q600 (signal meanings and combinators; verify exact shipped behavior).
- Yorven, circuit examples (2025): https://www.youtube.com/watch?v=R05jSixhI24 (oil cracking, power, trains; some mods shown, so do not assume all examples are vanilla).
- Continue official Wube Friday Facts research for current rules: https://factorio.com/blog/ .

**Warning about older tutorials:** 1.x fluid calculations, old train schedules, earlier combinator controls, and some old blueprint format pages predate 2.x. The Wiki's blueprint-string page and circuit cookbook expressly warn they need 2.0 updates. Do not treat these as complete authoritative 2.x specifications without game/API checks.

## How Zoo should use this reference

For R06/R07/R08 and each later milestone:
1. Find the relevant subsystem above and read the current official wiki/API release notes **for the installed version**.
2. Identify preconditions, exact prototype/recipe fields, supported actions, surfaces and permission mode.
3. Find matching case IDs in [FACTORIO_QUIRKS_AND_EDGE_CASES.md](FACTORIO_QUIRKS_AND_EDGE_CASES.md); add new candidate cases as issues arise.
4. Implement a deterministic fixture using verified game data, mark synthetic data as synthetic, and test negative as well as positive cases.
5. Get separate user approval for gameplay validation on a disposable save. Record expected outcomes and measured deltas; update R05 ledger evidence truthfully.
6. Do not assert "all Factorio quirks covered" or "works with any mod" without a bounded versioned evidence matrix.
