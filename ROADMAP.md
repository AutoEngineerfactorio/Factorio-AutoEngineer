# Development roadmap

This is a planning roadmap, not a promise of release dates.

The target is autonomous operation with human supervision: the agent plans and
executes routine actions within agreed limits, while the user can monitor, pause,
override or stop it. Risky or out-of-scope decisions require approval. Per-movement
approval remains a development safeguard until supervised autonomy is validated.

Complete and validate coverage of all areas of vanilla Factorio, including Space Age,
before starting modded compatibility work. Space Age is part of the vanilla scope
for this project. Modded gameplay is the final phase.

## Phase 0 — Tested proof of concept
- [x] Local LLM responds via llama.cpp
- [x] Connect Python MCP client to FactorioMCP
- [x] Read live player state
- [x] AI proposes and validates a movement
- [x] Execute supervised movement and verify position
- [x] Basic desktop UI approvals and logs

## Phase 1 — Safe, reproducible development release
- [x] Audit tool implementations and establish a strict dispatch boundary
- [x] Replace temporary RCON credentials and isolate configuration
- [x] Address dependency vulnerability warnings
- [x] Package only authorized project source, with tested installation instructions
- [x] Detect stalled, repeated, and failed movements reliably
- [x] Add concise, structured agent event logs

## Phase 2 — Intelligent exploration
- [x] Persistent visited-area and failed-target map
- [x] Objective-based navigation and path validation
- [x] Efficient discovery of nearby resources
- [x] Live 2D dashboard map and inventory display

## Phase 3 — Factory gameplay
- [ ] Runtime capability registry: version, enabled expansions, research, surface, quality and charted observation rights
- [ ] Durable goal graph and action journal: checkpoints, uncertain-result re-observation and duplicate-safe restart
- [ ] Deterministic recipe/rate solver, machine ratios, material bills, layout constraints and measured throughput
- [ ] Closed-loop shortage, brownout, fluid/heat, depletion and spoilage recovery
- [ ] Construction/logistic robot capacity, coverage, charging and legitimate material checks
- [ ] Separate Space Age platform engineering: asteroid processing, fuel, defense, cargo routes and safe return
- [ ] Quality-aware production/recycling solver: expected yields, uncertainty and measured outcomes
- [ ] Researched defense/combat, retreat/resupply, captive-spawner and biter-egg safety

- [x] Verified starter mining and crafting operations (bounded basic resources, gears and cable)
- [ ] Extend verified operations across vanilla and Space Age resources and recipes
- [x] Factorio-style dashboard map: terrain, water, resource patches, buildings, enemies, player markers, pan and zoom
- [x] Player-style inventory grid: item icons, stack counts and quality indicators; initially read-only
- [ ] Resource-aware factory building and placement checks
- [ ] Production, power, research, and recovery planning
- [ ] Enemy detection, threat avoidance, and defensive building
- [ ] Human-approved combat, equipment, ammunition, and recovery checks
- [ ] Blueprint creation, saving, and a reusable blueprint library
- [ ] Blueprint placement, material availability, and construction verification
- [ ] Logistics, trains, signals, fluids, circuits, modules, and beacons
- [ ] Pollution, enemy evolution, exploration, and expansion
- [ ] Base-game progression through rocket launch and endgame production
- [ ] Space Age planets, space platforms, interplanetary logistics, and progression
- [ ] Space Age quality, spoilage, elevated rails, and planet-specific production
- [ ] Human/AI task handoff

## Phase 4 — In-game companion
- [ ] Compact, expandable Factorio UI panel
- [ ] In-game plan visualization and status
- [ ] Manual pause/takeover and optional assistance
- [ ] Blueprint selection and combat-assistance controls
- [ ] Evaluate separate-player cooperative control feasibility

## Phase 5 — Vanilla completion and optional autonomy
- [ ] Fresh-save beginner factory, sustained production/research and complete victory acceptance scenarios
- [ ] Measured 1-hour/8-hour endurance, restart/network recovery, manual takeover and resource budgets
- [ ] Launcher start/attach/health/stop lifecycle, provider adapters and tested hardware profiles
- [ ] Separate optional game-version compatibility track; no automatic save migration

- [ ] Audit and validate all vanilla systems, including multiplayer and remaining edge cases
- [ ] Validate complete vanilla progression and recovery in the dedicated test save
- [ ] Safe unattended execution with budgets, watchdogs, and recovery
- [ ] Evaluate unattended combat only after supervised combat is validated
- [ ] User-friendly packaging and onboarding
- [ ] Complete the vanilla and Space Age acceptance checklist before modded compatibility

## Phase 6 — Modded gameplay (last)
- [ ] Separate Space Exploration profile and versioned spaceship adapter: hull/integrity, fuel, docking, cargo and victory
- [ ] Mod-specific megafactory/logistics integrations after vanilla and Space Age acceptance

- [ ] Runtime discovery of modded prototypes and recipes
- [ ] Validate selected mod and overhaul compatibility
- [ ] Revalidate movement, combat, blueprints, and safety for each supported mod

## Detailed planning and acceptance gates

The [reconciled work handoff](docs/WORK_HANDOFF_2026-10-18.md) and
[full-autonomy gap audit](docs/FULL_AUTONOMY_GAP_AUDIT_2026-10-18.md) expand the requirements and G0–G9 acceptance gates.
Their research leads are unverified until checked against primary sources and the installed game.
Space Age remains vanilla scope; Space Exploration is modded and stays in Phase 6.
G7 (SE) runs only after vanilla/Space Age completion, regardless of its numeric position.
All new tasks remain unchecked; planning does not establish implementation or test coverage.

Dashboard completion is scoped to the bounded read-only view; see [display validation and limitations](docs/DASHBOARD_MAP_VALIDATION.md). It stays live independently of AI execution.
