# Factorio AutoEngineer — Full-Autonomy Gap Audit and Space Systems Addendum

> Reconciled with published commit `099a4de93a76a48c2c81758521d7a519c1f66391` on 2026-10-18. This is planning context, not execution authorization. Phase 0–2 are complete at their documented scope; bounded starter mining/crafting is tested and published. Full vanilla/Space Age operations, the Factorio-style map and player-style inventory remain pending in Phase 3. See [current roadmap](../ROADMAP.md) and [validation record](VERIFIED_OPERATIONS_VALIDATION.md).
>
> Historical research claims below (model/GPU releases, Factorio 2.1, mod versions, mechanics and licensing) have not been independently verified in this reconciliation. They are research leads, not supported compatibility claims. Verify primary sources before implementation. Referenced addenda not included in this repository are unavailable context. No game, mod, save or license changes are authorized by this document.


**Date:** 2026-10-18  
**Project:** https://github.com/AutoEngineerfactorio/Factorio-AutoEngineer  
**Status:** Planning only. This document does not authorize editing the Windows workspace, mod profiles, saves, executable, or GitHub.  
**Reconciled baseline:** audited controller, movement/exploration memory, objective navigation, resource discovery and schematic dashboard are published; bounded starter mining/crafting passed 101 offline tests plus disposable-world validation. Full playthrough autonomy remains unproven.

## Executive finding

The previous roadmap already includes a Windows launcher, AI-provider chooser, validated actions, recipe math, blueprints, robots, trains, circuits, combat, mod support, Space Age, Space Exploration and 2.1 testing. **What is missing is a complete, measurable autonomy architecture** and three standalone engineering systems: (a) Space Age interplanetary space platforms, (b) Space Exploration's very different player-built spaceships, (c) stochastic quality engineering. Full autonomy must prove progression and recovery rather than merely accumulating individual tool integrations.

## Roadmap coverage versus true autonomy gaps

| Area | Existing roadmap | Missing or insufficient for full autonomy | Importance |
| --- | --- | --- | --- |
| Observation, safe movements | Prototype demonstrated | Chart/fog-of-war enforcement; staleness and no-op detection; real-time safe takeover; exact success semantics | Critical |
| Mining, crafting, placement | Tool inventory and some integration tests | End-to-end legitimate startup with zero resources; inventory/recipe/technology feasibility; recovering from depleted patches | Critical |
| Long-term planning | Qwen goal prompts, history notion | Persistent durable task graph, dependencies, checkpoints, goals per surface, resumption after reboot/model swap | Critical |
| Research & victory | Research tools listed and recipe solver planned | Autonomous lab/science supply; tech selection; victory criterion by profile (base, Space Age, SE), end-to-end playthrough tests | Critical |
| Factory reliability | Helmod-inspired math and optimization planned | Closed-loop telemetry, corrective maintenance, brownouts, fluids/heat/spoilage, fault and shortage root-cause diagnosis | Critical |
| Construction & blueprint library | Draftsman/blueprint studies, robot construction planned | Proven template versioning, quality-aware bill of materials, surface legality, mod hashes, construction sequencing | High |
| Networks/logistics | Belts, trains, circuits, robots planned | Train gridlock/deadlock recovery, circuit state debugging, throughput and charging under UPS constraints | High |
| Space Age space platforms | Mentioned in planetary logistics | Full platform design, fuel/oxidizer/asteroid recycling, defenses, route planning, cargo imports/exports, damage/recovery | Critical for Space Age |
| Space Exploration spaceships | Mod support mentioned | Spaceship console, enclosed hull/doors, structural and container stress, clamps/docking, schedules, travel fuel and mod-specific APIs | Critical for SE |
| Quality | Formulae mentioned in manufacturing | Stochastic production/yield optimization, quality-specific item flows, modules, beacons, recycling and quality-aware upgrades | High |
| Combat | Defenses, combat robots and egg farm planned | Escalation policy, retreat/repair/resupply, nest preservation, threat response without losing critical infrastructure | High |
| Multiplayer/cooperation | Shared-character pause/takeover planned | Arbitration/locks, independent-character feasibility, player orders, permissions and per-owner priorities | High |
| Deployment and safety | Launcher, backups and audit planned | Checkpoints, resume idempotency, process crash recovery, load shedding, credentials, dependency remediation, version migration | Critical |
| Mod compatibility | Prototype registry proposed | Runtime capability discovery, mod settings/version signatures, fallback for unknown recipes/surfaces, repeatable SE tests | Critical |
| Evaluation | FLE-inspired testing proposed | Scenario matrix, objective pass/fail metrics, 1h/8h soak tests, quality and platform profiles, deterministic replay | Critical |

### Foundational rule: autonomous objectives should be validated world-state transitions

Model proposes an objective and candidate action. Deterministic services own planning calculations and side effects. Before execution verify force, research, inventory, surface, charted visibility, action range, relevant prototypes, player control state and permissions. After execution measure observed delta and update durable state. **Never equate tool return value with proof of success** (movement regression already demonstrates why). Every destructive or combat operation remains supervised until independently audited and explicitly enabled by the player.

## A. Space Age — autonomous space-platform engineering

**Separate adapter:** `SpaceAgePlatformPlanner`, `PlatformLogisticsController`, `AsteroidThreatModel` (not an SE spaceship adapter).

1. **Unlock/build:** Check researched technology, materials, rocket capacity, build-permitted platform surface, platform hub and minimum functional power. Assemble a reproducible platform blueprint in segments using legitimate supplied materials and normal robot construction.
2. **Resource/mass balance:** Read actual asteroid collection/collision rates by orbit and route; model collectors, crushers, metallic/carbonic/oxide resource flows, alternative recipes, fuel/oxidizer, ammunition, buffer fullness and discard/recirculation. Constrain by item throughput, fluid production, machine energy, storage, platform size/mass and thruster efficiency.
3. **Flight and routes:** Compute trip times and payload capacities; schedule safe launch/departure, orbital stops, waiting, pickup/delivery requests and rocket shipments. Require fuel and ammunition reserve for destination and planned return, or model one-way trips explicitly.
4. **Survival/recovery:** Model asteroid class/resistance and defense coverage, turret ammo consumption, platform health, power deficits, damage to vital production, stuck orbital requests; fail safe if reserves insufficient. Make 2.0/2.1-specific asteroid-damage assumptions versioned.
5. **Fleet economics:** Multiple platform types (small shuttle, bulk cargo, orbital manufacturing, deep-space expedition), route frequency, reliability, capital and operating cost. Treat interplanetary items as a time-expanded transport network.
6. **Verification:** Compare predicted/actual travel time, sustained asteroid supply, fuel stock, rockets and cargo delivery, damage and 60-minute survival. Build a platform that can reliably transport specified items and safely return before attempting endgame travel.

**Performance caution:** In 2.1, Wube changed space logistics and asteroid impact rules; query version and current game state. Do not apply 2.1 behavior to user's 2.0.77 baseline.

## B. Space Exploration — autonomous player-built spaceships (mod-only)

**Separate adapter:** `SESpaceshipPlanner` + versioned mod integration; keep SE and official Space Age in different game/mod/save profiles.

1. Read **SE mod version, API/prototypes, technologies and permitted surface**. Treat 2.0/2.1 SE variants differently; SE 0.7.63 requires Factorio 2.1.22+ according to its dated changelog.
2. Plan contiguous spaceship floors, fully enclosed hull/doors, consoles, engines, boosters, power, life-support requirements where applicable, weapons, cargo and docking clamps.
3. Validate **structural integrity, container stress**, engine efficiency, travel energy/fuel, cargo loading/unloading, destination and safe docking/clamp availability before launch.
4. Support the mod's spaceship **scheduler, stops, clamp priorities, wait conditions and interrupts** when exposed through audited mechanisms, otherwise present manual instruction instead of raw Lua execution.
5. Plan ship classes (cargo, passenger, military, explorer, late-game victory) and resource movement among surfaces/asteroid belts. Avoid assuming Space Age rocket/platform hub logistics apply to SE.
6. No redistribution of SE mod code or assets; user installs from official source. Test in pinned isolated save, with mod API discovery and explicit human approval for new gameplay capabilities.
7. Verification: detect ship valid/invalid and why, genuine takeoff, flight and landing; delivered correct items; recovered from no-fuel/docking errors; protected player and saves. **Endgame SE success** must be derived from installed version's real victory conditions.

## C. Quality — mathematical, probability-aware factory planning

**Separate service:** `QualityYieldSolver` that extends recipe graph and blueprint BOM; quality levels are item/entity identities where supported and researched; when the Quality mod is disabled the engine falls back to regular production. The 2.0 Space Age and 2.1 dependency rules differ, so version and enabled-mod detection are mandatory.

- Build quality-indexed flows for normal/uncommon/rare/epic/legendary **only as available in active modpack**, including mods that change or add quality tiers. Distinguish fluids (no quality in native mechanics) from items.
- Model quality chance of each machine/module and the effects of product quality, recipe input-quality rules, speed penalties, productivity/research, beacon bonuses, and recycling/scrap return distributions. Do not treat probabilistic output as guaranteed.
- Compute expected yield *and* uncertainty, input cost per target-quality output, expected energy and time, storage/buffer requirements, recycling feedback loop stability and quality sorting. Detect throughput starvation or inventory gridlock from mixed-quality material.
- Select strategically valuable upgrades—e.g., long-range defenses, platform solar/collectors, high-quality bots, beacons, assemblers, train rolling stock in 2.1—only where amortized gain exceeds acquisition cost.
- Compare at least three policies: all normal-quality throughput, dedicated quality-upgrade line, and recycle-until-quality target. Optimize to objective (cost, space, power, UPS, sustained output) with confidence estimates and user-visible trade-offs.
- Test stochastic projections against repeated actual game outcomes and high-quality blueprints; do not generate fictitious higher-quality items. Respect 2.1 changes such as quality-module disallowance in asteroid reprocessing and quality-enabled train upgrades.

## D. Additional gameplay gaps for an end-to-end autonomous playthrough

1. **Progression orchestrator:** Start with no factory; choose tech, science packs and lab supply; unlock tools; automatically establish initial power, mining/smelting, circuits, oil, chemical science, advanced production, rockets, expansion and victory. Use a profile-driven tech/goal graph, not hardcoded sequence beyond test baselines.
2. **Physical environment:** Water/cliffs/trees/terrain clearing, landfill/foundation/bridges/elevated rails, landfill permissions, collision/pathfinding, remote view and explored map limitations. **Do not allow remote resource scans to reveal unexplored terrain** unless observation rights are independently proven.
3. **Power/fluid/heat:** Brownout prediction, boiler/fuel sourcing, steam/nuclear/solar/accumulator dispatch; fluid pressure/throughput, temperature/heat, pumps and storage; reserve energy for critical defenses and bots.
4. **Decay and perishables:** Gleba spoilage, nutrients/cultivation, bacteria loops, agriculture production, platform perishables where applicable; aging inventory and safety buffers. Aquilo heating/temperature constraints, Vulcanus lava/metallurgy, Fulgora scrap/recycling/electromagnetics. Unlock by actual game state.
5. **Threat and survival:** Enemy evolution/pollution, turrets/ammo/repair capacity, combat vehicle/weapon progression and casualties; long-term rebuild prioritization. Emergency stops, retreat, resupply, combat approval and protection of nests needed for egg farms.
6. **Production runtime:** Depletion forecasts, alternate resources and byproducts, excess-output management, item congestion, belt/pipe/trains/bot redesign and UPS optimization.
7. **Recoverability:** Durable event journal with per-action ID, completed/pending checkpoints, safe resume after agent/model/server restart, idempotency tests, replay and save snapshots (no automatic modification of personal saves).
8. **Cooperative operation:** Manual takeover and capability arbitration so player and agent never control the same character simultaneously; candidate separate character/remote-view integration feasibility test.
9. **General modpack support:** Tech/entity/recipe prototypes + mod-list/settings hash, surfaces, fluids, recipes, quality and enemies; feature detection; adapter-specific tests and permissions. No assumptions that modded enemies or recipes match vanilla names.
10. **Public alpha safety:** Signed/reproducible-ish builds where practicable, dependency security, no RCON password in repository, local-only network by default, update/migration rollback and performance reports. Explicit disclaimer of experimental autonomy.

## E. Architecture and state machine

```text
Player goals / presets (vanilla victory, Space Age victory, SE victory, megabase, assistant)
  -> Capability registry (game version, mod list, technology, surface, quality)
  -> Persistent goal dependency graph + checkpoint journal
  -> LLM strategic planner (provider/model independent)
  -> Deterministic production + logistics + platform/ship + quality solvers
  -> Constraint/permission/safety checks (charted knowledge and no-cheat rules)
  -> Supervised action dispatcher (MCP allowlist; no raw Lua/RCON in LLM API)
  -> Actual in-game observations and telemetry
  -> Measured success/failure + anomaly recovery + dashboard/in-game explanations
  -> Resume / replan / pause / require player help
```

**Proposed durable action states:** `proposed -> validated -> approval_pending -> executing -> outcome_observed -> verified|failed|uncertain -> checkpointed`. On restart, `executing/uncertain` states must be reobserved before any retry; never duplicate irreversible work.

## F. Milestones and objective acceptance gates

| Gate | Minimum proof | Stage |
| --- | --- | --- |
| G0: Stable supervised controller | Published movement and safety regressions provide evidence; retain regression checks as capabilities expand | Baseline covered; ongoing regression |
| G1: Legitimate beginner factory | Starts isolated fresh save; finds charted ores; mines and crafts normally; powers smelting and first assembler; no cheats | Foundational |
| G2: Sustained production/research | Sustains ≥30 minutes of specified production; corrects starvation/brownout; unlocks an identified technology with real science packs | Foundational |
| G3: Validated blueprints and bots | Generates from recipe graph; creates ghosts from actual resources; builds with legitimate character/bots; validates observed throughput | Intermediate |
| G4: Automated circuits/trains | Builds safe rail/signal layout and solves block occupancy; circuits maintain inventory thresholds; detects and resolves a train deadlock | Intermediate |
| G5: Space Age platform | Completes a supervised, safe interplanetary cargo trip and return with proper fuel/defense, records delivery, sustains ≥60m route | Advanced |
| G6: Quality math | Compares quality/recycling policy predicted yield to measured sample; respects actual mods and tech; upgrades blueprint without loss | Advanced |
| G7: SE spaceship | In separate SE profile, builds/validates hull and launches, delivers cargo, docks and returns without losing save | Advanced mod |
| G8: Playthrough completion | In a known test seed, completes vanilla rocket victory; later reaches Space Age solar-system edge; SE-specific victory as supported | Long-term |
| G9: Unattended endurance | Hours-long measured operation, bounded resources/VRAM/UPS, recovery from interrupted process/network and shortage; audit log and manual takeover works | Long-term |

**Policy:** no automatic full-autonomy toggle until the specific capabilities being automated passed regression/soak testing; maintain user-selectable supervised controls, safety budget and pause. Missing tool support must yield a clean, explained stop or ask for help, not invented actions.

## G. Technical research links (official / primary)

- Space Age platforms: https://www.factorio.com/blog/post/fff-381
- Space Age game / victory: https://wiki.factorio.com/Space_Age
- Quality: https://wiki.factorio.com/Quality and https://www.factorio.com/blog/post/fff-375
- Factorio 2.1 platform asteroid changes: https://www.factorio.com/blog/post/fff-448
- Factorio 2.1 logistics / train quality changes: https://www.factorio.com/blog/post/fff-441 and https://www.factorio.com/blog/post/fff-442
- Space Exploration mod: https://mods.factorio.com/mod/space-exploration
- Space Exploration changelog/scheduler/integrity: https://mods.factorio.com/mod/space-exploration/changelog
- Verified game, mod and dependency versions must be checked again before code is changed or new profiles installed.

**Authorization:** Research and planning only. The project owner must approve specific file changes, installs, testing of gameplay actions, migration and any GitHub updates/publishing.
