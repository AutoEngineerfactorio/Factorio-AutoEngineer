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
- [x] Three operating modes enforced at dispatch: AI Helper (default; no gameplay writes), Semi-Autonomous (approved actions/batches), Fully Autonomous (visibly locked until acceptance gates pass)
- [ ] Mode-switch and manual-takeover arbitration: revoke pending permits, cancel owned actions, reject stale approvals, re-observe before resume; emergency stopping remains available in every mode
- [ ] Per-mechanic coverage matrix: profile/version, observe, plan, validated action or justified N/A, outcome verification, mode permission and regression evidence
- [ ] Read-only research/recipe/machine snapshots and Helper browser, with freshness, unlocks, surface conditions and profile fingerprints
- [ ] Helper production-target calculator: 300 gears/minute benchmark, explicit utilization margin, alternative plans, supply/transport/power limits and measured-versus-predicted rates
- [ ] Safe blueprint/book/parameter codec and import/export: size/depth limits, version checks, preserved circuit/recipe/quality fields and round-trip tests
- [ ] Private blueprint library and preview: immutable revisions, provenance/redistribution rights, checksums, material bills and missing-prototype detection; no live placement in Helper mode
- [ ] Typed circuit compiler: signal/wire validation, hysteresis, tick latency, feedback/power-loss recovery and measured truth-table tests
- [ ] Train capacity and safety planner: payload/round-trip rates, station buffers, signals/interrupts, refueling, congestion and deadlock recovery
- [ ] Supervised single-block self-expansion: demand deficit, feasible design, approval, legitimate ghosts, real train/bot material supply, physical construction and measured production
- [ ] Expansion checkpoints and bounded recovery: no duplicate blocks after restart/retry, no phantom materials, protected player structures and explicit demolition approval
- [ ] Engineering dashboard workspace: tech/recipe explorer, item/fluid/equipment views, production/power graphs, blueprint previews, train/bot overlays, threats, job queues and observed-versus-estimated values
- [ ] Attach/health/configuration foundation for existing services, without duplicate starts or stopping user-owned processes; full executable packaging remains Phase 5
- [ ] Chart/fog and stale-state acceptance tests across every observation adapter, beyond the completed bounded dashboard map

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
- [ ] Enable Full Autonomy only for individually validated capabilities and an explicit save/profile, mission, zones, budgets and risk policy; no self-expanding permissions
- [ ] Multi-block self-expansion endurance: shortage/congestion recovery, restart idempotency, manual takeover and bounded telemetry/UPS at increasing factory sizes
- [ ] Provider/model selection and capability tests: schema compliance, cancellation, latency and safe actions; hardware free-VRAM/context checks distinguish loading from gameplay validation
- [ ] Windows one-folder executable and startup wizard: isolated profiles, process ownership, readiness/port checks, secure credentials and reproducible install/attach/shutdown tests

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
- [ ] Optional LTN, Cybersyn and Recursive Blueprints+ adapters, with explicit opt-in, license/version checks and no required mod dependency
- [ ] Extend the validated expansion/blueprint/solver pipeline to modpacks only after vanilla and Space Age completion

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

## Coverage and sequencing contract

AI Helper, Semi-Autonomous and Fully Autonomous are permission modes; Navigate/Mine/Craft are tasks, not substitutes for those modes. Helper permits read-only game observations and user-selected local blueprint save/import/export, but no gameplay execution. Controller-owned emergency cleanup is always available. Switching to a less permissive mode cancels pending gameplay work; the model cannot grant itself permissions. Full Autonomy never authorizes installs, account/GitHub changes, save migration or access outside the selected gameplay scope.

The mechanics matrix must cover character survival/death/vehicles; discovery and charted knowledge; manufacturing; belts/inserters/storage; fluids/heat/power; science/research/victory; modules/beacons; construction/deconstruction; robots; rails/signals/schedules; circuits; combat/defense; world dynamics; and cooperative control. Base-only and first-party expansion profiles require separate evidence. Space Age, Quality and Elevated Rails remain within this project's vanilla completion scope; separate testing does not move them to the modded phase.

Self-expansion proceeds from offline math and blueprint preview/library to one supervised block, then real construction supply and measured production, then Phase 5 multi-block endurance/autonomy. Vanilla circuits regulate demand and delivery; they do not themselves grant arbitrary blueprint placement. Space Age platform and quality variants are validated before modded integrations.

Repository Phases 0-6 are the canonical delivery order. G0-G9 are acceptance gates, not replacement phase numbers; engineering documents' internal stages must be mapped to them. G1/G2 require a legitimate beginner factory and sustained research, G3/G4 blueprint/bot/circuit/train proof, G5/G6 Space Age platform and quality proof, G8 vanilla/Space Age completion and G9 endurance. G7 Space Exploration remains Phase 6 after vanilla completion. Use dedicated isolated fresh-start scenarios when needed, while retaining the reusable save for routine regression tests.

Historical starter documents, old tool counts and pending-license/setup claims do not override published implementation status. Compatibility catalogs are research candidates until primary-source checks and capability tests pass. New requirements above are unchecked; completed starter operations and bounded dashboard milestones retain their documented limits.

Three-mode permission enforcement and the locked Full choice are tested; [mode behavior and validation](docs/OPERATING_MODES.md). Helper recipe/blueprint planning and full takeover arbitration remain separate unchecked work.
