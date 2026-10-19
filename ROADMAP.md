# Development roadmap

This is a planning roadmap, not a promise of release dates. See also the [October 19 development decisions](docs/DEVELOPMENT_DECISIONS_2026-10-19.md) for the current three-mode priority, online reference research, time-tools guardrails, Zoo Code review and pY benchmark agreement.

The target is autonomous operation with human supervision: the agent plans and
executes routine actions within agreed limits, while the user can monitor, pause,
override or stop it. Risky or out-of-scope decisions require approval. Per-movement
approval remains a development safeguard until supervised autonomy is validated.

Complete and validate coverage of all areas of vanilla Factorio, including Space Age,
before claiming third-party modded gameplay compatibility. Space Age is part of
the vanilla scope for this project. Full modded gameplay remains the final phase.
**Continuous development exception:** benchmark R04–R06 data handling and solver
complexity against synthetic pY-shaped scenarios now, then version-pinned, read-only
Pyanodons (pY) catalogs in a separate isolated test profile once the safe telemetry
adapter exists. This is early performance/architecture testing, **not** an R20
gameplay acceptance claim. See [continuous modded benchmarks](docs/CONTINUOUS_MOD_BENCHMARKS.md).

## Complete roadmap index: R01-R20 (read this before selecting the next Zoo task)

**The R milestones continue through R20. R09 is not the end of the project.**
R01-R09 establish safe control, game-aware engineering, blueprint construction and the first supervised self-expansion. R10-R16 cover circuits, trains, robots, recovery, combat, Space Age and quality. R17-R20 cover in-game cooperation, full progression and endurance, public onboarding and then modded Factorio.

**How to interpret status:** "Published / offline tested" describes source or unit-test evidence **only**, not complete gameplay acceptance. Milestones with open real-world tests remain open. The canonical detailed, version-aware acceptance criteria are in [R01-R20 planning requirements](docs/PLANNING_REQUIREMENTS.md); this table is a navigation index, not a replacement. Phases 0-6 describe delivery order and G0-G9 are separate acceptance gates.

| Requirement | Delivery phase | What the AI is being taught | Evidence / next work |
|---|---|---|---|
| **R01 - Human control** | 3 | Stop, manual takeover, cancel stale approvals, re-observe before resume | Tested local foundation, scope-limited |
| **R02 - Safe launcher** | 3 | Start/attach/check/stop only owned services; Windows launcher prototype | Tested local prototype; public setup still R19 |
| **R03 - Durable jobs** | 3-5 | Remember goals, actions, uncertainty and crash-safe restart without duplicates | Tested journal foundation; full graph later |
| **R04 - Game capability truth** | 3 | Observe actual game version, enabled content, research, recipes, machines, surfaces and freshness | Snapshot source/offline tests published; live coverage open |
| **R05 - Mechanics evidence ledger** | 3-5 | Record observed/planned/permitted/verified/regression evidence per mechanic and profile | Ledger source/offline tests published; broad live proof open |
| **R06 - Production mathematics** | 3 | Solve recipes, catalysts, cycles, fluids, probability, modules, quality, power and supply; 300 gears/min fixture | **Local work in progress**; acceptance open |
| **R07 - Blueprint fidelity** | 3 | Safely read/write blueprint strings, books and parameters; maintain private revisioned library | **ON HOLD** until [R04-R06 pre-R07 acceptance](docs/R04_R06_PRE_R07_ACCEPTANCE.md) |
| **R08 - Build feasibility** | 3 | Validate terrain, collision, item bills, belt/pipe/inserter/rail/wire/power connections | Planned |
| **R09 - First self-expanding block** | 3 then 5 | From demand to approval, real materials, physical construction and measured throughput | Planned; does **not** unlock Full Autonomy |
| **R10 - Circuit networks** | 3 | Type-check signals, combinators, red/green wires and real feedback/latency behavior | Planned |
| **R11 - Railway engineering** | 3 then 5 | Rails, signals, train limits, schedules/interrupts, refueling, throughput, congestion/recovery | Planned |
| **R12 - Three robot types** | 3 | Construction, logistics and temporary combat robots; charging, reach, inventory and costs | Planned |
| **R13 - Factory recovery** | 3 | Repair shortages, blocked production, power/fluid/heat faults, spoilage and depletion | Planned |
| **R14 - Defense, combat and eggs** | 3 then 5 | Research-appropriate defenses, safe supervised combat, biter eggs and captive spawners | Planned |
| **R15 - Space Age platforms** | 3 then 5 | Space logistics, asteroid processing, platform construction, power, fuel, defense and routes | Planned |
| **R16 - Item/entity quality** | 3 then 5 | Quality-aware inventories, upgrade/recycling probabilities and cost/rate tradeoffs | Planned |
| **R17 - In-game companion UI** | 4 | Show plans and approvals in Factorio; pause/stop/takeover and cooperate safely | Planned |
| **R18 - Progression and endurance** | 5 | Start-to-victory proof, megafactory scalability, recovery and long-duration tested autonomy | Planned |
| **R19 - Public launcher and providers** | 5 | Install wizard, one-folder release, model/hardware profiles, upgrades, secure onboarding | Planned |
| **R20 - Third-party mods (last)** | 6 | Versioned adapters for Space Exploration, LTN, Cybersyn, Recursive Blueprints+ and modpacks | Planned **after** vanilla + Space Age acceptance |

### Required Factorio knowledge for every milestone

Zoo Code, Cline and other coding agents must consult [Factorio mechanics and Space Age reference](docs/FACTORIO_MECHANICS_REFERENCE.md), the [Lua scripting and mod API reference](docs/FACTORIO_SCRIPTING_API_REFERENCE.md), [quirks / edge-case test catalog](docs/FACTORIO_QUIRKS_AND_EDGE_CASES.md), [open coverage gap register](docs/FACTORIO_COVERAGE_GAP_REGISTER.md), and [the R01-R20 acceptance requirements](docs/PLANNING_REQUIREMENTS.md). These documents link to live official Factorio documentation; they do **not** replace authoritative game prototype/runtime data. Record the exact game version, enabled base/Space Age/Quality/Elevated Rails content, mods, surface, force, research state and observation rights for relevant tests.

**Current development gate: Finish [R04-R06 pre-R07 acceptance](docs/R04_R06_PRE_R07_ACCEPTANCE.md) before any R07 code.** The bridge and offline calculations are not proof of live recipe telemetry, full flow balance or Space Age support.

**No milestone is completed merely by a model response, video, unit test or generated blueprint.** Real-world acceptance needs separately authorized fixtures and observed game outcomes. Keep Full Autonomy locked until its safety gates pass. The next engineering milestone is R06; then continue through R07-R20 under their stated dependencies and phase order.

## Planning guidance and delivery order

All 24 files in the reviewed complete planning archive now guide requirements, design and acceptance evidence, including `SOURCES_AND_PROJECT_STATUS.md`. The [requirements and file-by-file mapping](docs/PLANNING_REQUIREMENTS.md), [research sources](docs/PLANNING_SOURCES.md) and [archive manifest](docs/PLANNING_ARCHIVE_MANIFEST.json) preserve their scope. Archived prompts, paths, tool counts, license status, old checkmarks and unverified release-watch claims are historical context, not new execution instructions or current implementation evidence.

Next delivery order: safe human takeover and service attachment; a locally tested launcher executable prototype; live capability/research/recipe data and the Helper calculator; blueprint codec/library/preview; legitimate single-block construction; circuits, trains, robots and defense; Space Age platforms/quality and progression; endurance and public packaging; finally third-party mods. Shared deterministic services support all three operating modes. The language model selects goals and explains options; code calculates recipes, rates, geometry and feasibility.

Completed work retains its documented scope. Requirements are checked only for their documented tested scope; later acceptance remains unchecked. Emergency stopping and the five-tile development movement limit remain active.

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
- [x] **R01–R03: tested local foundation:** manual takeover arbitration, owned-service start/attach/health/stop, and the Windows one-folder launcher prototype. Real input, live crash checkpoints, readiness, port/duplicate checks, cancellation, source/frozen Stop, actual GUI restart/shutdown and save integrity passed. See [validation](docs/FOUNDATION_VALIDATION.md); production graphs, clean-PC onboarding and endurance remain later work.
- [ ] **R04–R06: Helper engineering:** live profile/research/recipe/machine snapshots, per-mechanic coverage evidence, and deterministic production math; prove the 300 gears/minute fixture and compare alternatives
- [ ] **R07–R09: construction pipeline:** bounded faithful blueprint/book codec, private revisions/preview, placement validation, real materials, physical completion and measured throughput; ghosts alone do not count
- [ ] Production acceptance: multi-output/cyclic/catalyst/probabilistic flows, fluid temperatures, legal machine/module/beacon/quality effects and supply constraints; compare predicted production with 1/5/10-minute measurements
- [ ] Robot acceptance: distinct construction, logistic and temporary combat-robot adapters; coverage, payload/travel/charging, shortages and real costs; Stop prevents new actions without claiming to undo independent game jobs
- [ ] Circuit/train acceptance: typed signals/ports/wires, red/green isolation, hysteresis, tick latency and power-loss recovery; safe two-station route, interrupts/refueling, failed/full destinations, deadlocks and a 20+ train fixture

- [x] Three operating modes enforced at dispatch: AI Helper (default; no gameplay writes), Semi-Autonomous (approved actions/batches), Fully Autonomous (visibly locked until acceptance gates pass)
- [x] Mode-switch and manual-takeover arbitration: revoke pending permits, cancel owned actions, reject stale approvals, re-observe before resume; emergency stopping remains available in every mode
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
- [x] Attach/health/configuration foundation for existing services, without duplicate starts or stopping user-owned processes; full executable packaging remains Phase 5
- [ ] Chart/fog and stale-state acceptance tests across every observation adapter, beyond the completed bounded dashboard map

- [ ] Runtime capability registry: version, enabled expansions, research, surface, quality and charted observation rights
- [x] Durable goal/action journal foundation: persistent goal, sequential action dependencies, checkpoints, uncertain-result re-observation and duplicate-safe restart; full production graph expansion follows R06/R09
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
- [ ] Scaling acceptance: independently benchmark recipe solvers at 100/1,000/10,000 science per minute, and bounded telemetry/UPS at 100/1,000/10,000+ physical entities; report actual hardware and limits
- [ ] Reproducible public alpha: sanitized build/dependency manifests, model/license provenance, clean installation/attach/shutdown, updates and rollback; signing where practical; no game assets, private saves, credentials or model weights bundled

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

The [archive-derived requirements R01–R20](docs/PLANNING_REQUIREMENTS.md) provide the acceptance detail for all phases, including vehicles/death/recovery, science/victory, fluids/heat/spoilage, combat/egg safety, platform cargo/return, quality distributions, provider/hardware onboarding, co-op and the final modded adapters. Each implementation records its fixture, profile/version, expected and observed outcome, permission mode and evidence. A design reference or successful model load never checks off gameplay support.


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

### Launcher and map preview (October 18, 2026)
- [x] Local Windows one-folder launcher prototype: start/attach readiness, process ownership, profile validation, collision checks, cancellation, service health and verified owned shutdown. See [scope and setup](docs/LAUNCHER.md). Full public installer remains Phase 5.
- [x] Read-only local map overlays: pollution, electric supply/connections, logistics/construction coverage, nominal turret range, station names and force tags; tested with temporary fixtures. See [bounds and evidence](docs/MAP_TELEMETRY.md).
- [ ] Extend map browsing beyond the local window, surface selection and search; remote commands require separate mode-aware validation.

Current work: R04/R05 source and offline tests are published with full live acceptance still open; R06 deterministic production solver is in local development. The roadmap explicitly continues through **R20**: R07-R09 blueprint and first expansion, R10-R16 circuits/trains/robots/recovery/defense/Space Age/quality, R17-R19 interface/endurance/public onboarding, and R20 third-party mods last. The full R01-R20 index above and docs/PLANNING_REQUIREMENTS.md govern Zoo's next tasks.
