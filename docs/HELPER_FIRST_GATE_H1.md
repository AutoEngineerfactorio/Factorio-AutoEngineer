# Factorio AutoEngineer — Helper-first roadmap amendment

**Approved development-sequencing contract · 2026-10-19**

**Status:** Accepted for roadmap planning and integrated with the project's existing R01–R20 requirements. This is a planning and acceptance contract, not a claim of completed implementation. No live service, save, modpack or game version is changed by this document.

## Binding priority change

AutoEngineer will **finish and independently validate AI Helper and the Dashboard before expanding Semi-Autonomous or Fully Autonomous gameplay**. Retain existing R01-R03 safety/launcher/job foundations, including Stop, takeover, bounded movement, permission gating, crash safety, and read-only mode. Existing supervised operations may still be used in explicitly approved isolated regression testing; they are not authorization to build out autonomy early.

"Perfect" means **passed, measurable acceptance criteria for the declared supported versions, profiles, and features**—not a promise of zero bugs or universal support for every future mod/version. Unsupported states must be reported clearly, not guessed.

## Proposed implementation order

| Delivery track | Existing requirements | Objective | User-facing outcome |
|---|---|---|---|
| Foundation: preserve and harden | R01-R03 | Safe startup, service ownership, Stop, human takeover, bounded tool dispatch, durable jobs, rollback | Stable foundation; no expansion of autonomy |
| **Phase 1A: AI Helper + Dashboard** | R04-R06, R05 telemetry | Reliable live observation; recipe/research browser; all-product and fluid planning; power/production graphs, research unlocks, bottlenecks, recommendation explanations | A useful engineering assistant with **zero gameplay writes** |
| **Phase 1B: Blueprint Studio** | R07 and read-only/preflight elements of R08 | Generate, import/export, revise, preview, validate footprints, recipes, wiring, technology, modules and material cost, with clear current-versus-future buildability | User can inspect and save compatible blueprints, without placing anything |
| **Phase 1C: Discovery and Compatibility** | R04, R07, relevant R20 read-only discovery | Research community designs using authorized internet/video sources; record creator, source, license and version; validate actual mods, technology, surface, and prototypes | Find/compare/adapt designs for current vanilla/Space Age or known modded profiles; unsupported marked explicitly |
| **Gate H1: Helper + Dashboard acceptance** | New mandatory milestone | Deterministic tests, live data, UI visual QA, security, stress and restart/resume evidence for scoped supported profiles | Helper is demonstrably ready; user signs off before expanding gameplay |
| Phase 2: Semi-Autonomous | Gameplay portions of R08-R09, R10-R16 as unlocked | Authorized construction, logistics, train/bot interaction, factory operations, safe recovery and measured output; approvals retained | AI can perform user-approved actions and verify results |
| Phase 3: Fully Autonomous | R09-R20 and independent safety/endurance gates | Bounded goal selection, technology progression, autonomous operation with strong Stop/takeover and long-run verification | Full autonomy only after separate explicit gate and approval |

R-milestone numbers remain stable for traceability, but **delivery sequencing is controlled by this helper-first gate**. R07's *non-gameplay* blueprint functionality must not be delayed merely because physical construction is a later R08/R09 capability. Likewise, Helper's blueprint features do not lift the R04-R06 data-truth prerequisites. Do not weaken the existing safety requirements in the process.

## AI Helper required functional scope

1. **Game-aware inventory of capabilities:** Detect pinned game version, active force/surface, enabled Space Age/Quality/Elevated Rails or mods, their versions, research status, recipe/prototype availability, and observable machine capabilities. Separate "researched/buildable now" from "unlockable later" and "unsupported".
2. **Generalized production engineer:** For any supported item, fluid, science pack, ingredient, byproduct or applicable quality variant, accept configurable target throughput; solve real recipe graphs, shared inputs, recycling/catalysts, probabilities, energy, machine limits, logistics and bottlenecks. Offer multiple feasible designs. Never substitute a 300-gears/min fixture for all-output coverage.
3. **Power and production diagnosis:** Actual observed production/consumption counters, electric-network capacity/satisfaction, reserves, brownouts, stale-data warnings and cause-specific recommendations. Keep model prediction, synthetic replay and live measurement as separate evidence levels.
4. **Blueprint authoring and library:** Generate/import/export version-aware bounded blueprint strings/books/parameterized designs with private revisions, source attribution and material bills; fidelity and preview must be independently tested. Absolutely no placement in Helper mode.
5. **Community blueprint research:** Search approved websites and YouTube descriptions/linked blueprints; treat web content as untrusted; honor source license/creator; never execute arbitrary Lua or external code; independently validate prototype IDs, recipes, quality, research, mods and game version. Rate-limit research and cache provenance. Do not copy designs when redistribution rights are absent.
6. **Dashboard:** Functional map, inventory and research panes, production/power visualizations, diagnosis, plan alternatives, blueprint editor and preview, import/export, status/alerts, history and accessibility. Clear timestamps, units and unavailable states; no invented open-loop "success" statuses.
7. **Reliability:** Handles absent backends, stale telemetry, partial recipe pages, invalid blueprints, network failures, saves restarting, game version changes, renderer failures and AI provider timeouts without losing the ability to stop and recover.

### Modded compatibility policy

Recognize an active modded game and its prototype/recipe signature **during Helper mode**. Permit read-only catalog browsing and planning for mods only when data/recipes/blueprints have passed adapter-specific checks. Do not promise universal modded blueprint generation from a version label alone. Full third-party gameplay automation remains R20 unless deliberately re-scoped through an explicit review.

## Gate H1 — measurable acceptance checklist

- **Safety:** Helper cannot issue gameplay writes, unrestricted Lua/RCON, bypassed research, hidden-state observation, uncontrolled network access or unsafe blueprint placement. Test denial paths as well as happy paths.
- **Correct live data:** Confirm source, freshness, tick, force, surface, version, enabled content and research. Partial/missing data stays disabled or marked unknown.
- **All-product architecture:** Demonstrate generic planning across representative item, intermediate, science, multi-stage, fluid, quality, catalyst/recycling and modded-adapter cases as available. Maintain a per-output compatibility/coverage matrix and never claim untested items are verified.
- **Measured realism:** Validate predictions against real production and power telemetry, including exact 1/5/10-in-game-minute rates for selected physical, legit-built test factories. Document deviations, shortages, buffering, belts/inserters and UPS caveats. Synthetic demonstrations remain labelled synthetic.
- **Blueprint fidelity:** Versioned decode/encode round trips, unsupported entities and hostile input rejection, material/research/geometry checks, attribution, and safe saved revision/export. No Helper gameplay writes.
- **Visual correctness:** Pillow-assisted screenshot/diff and actual Windows UI testing at relevant resolutions for dashboard, blueprint preview, production/power charts and errors. Image tests do not replace underlying telemetry checks.
- **Failure and recovery:** Closed backend, stale data, truncated pages, invalid API/recipe, user interruption, save restart, and local model timeouts. Explain diagnosis; remain read-only.
- **Performance:** Real measured dashboard refresh/latency, bounded telemetry payloads, memory/CPU/VRAM/UPS impact and a recorded endurance run (duration and hardware stated). Establish thresholds based on actual machine measurements rather than inventing numerical claims.
- **Evidence:** Versioned test results, repeatable fixtures, approved disposable saves, known limitations, per-feature pass/partial/blocked states, and a user-reviewed Gate H1 checklist. A passing offline unit suite alone does not certify this gate.

**No Semi-Autonomous feature expansion or Fully Autonomous development before H1 is accepted.** Existing R01 supervised safety tests and critical fixes are exempt from the development freeze only if separately approved and executed in isolated test profiles. **Fully Autonomous requires its own later gates and explicit approval; H1 alone does not unlock it.**

## Continuous modded stress-testing

Throughout Phase 1A–1C, run isolated synthetic Pyanodons (pY)-shaped regression benchmarks for recipe graph scale, cycles, byproducts, memory/latency and UI staleness. When a safely versioned read-only adapter is qualified, separately benchmark the actual full pY suite against an isolated mod/save/write-data profile; do not combine it with Space Exploration or first-party expansion profiles by default. Modded Helper read-only discovery and qualified planning may be developed early, but R20 live third-party gameplay automation and compatibility claims remain separate and unaccepted.

## Integration and coordination

- Preserve all in-progress Copilot/Zoo R04-R06 changes, existing local rules/skills and pending test-world resources. Check Git status and file hashes before editing.
- Merge this roadmap amendment in bounded changes: two files or fewer and at most 120 changed lines per chunk, with source inspection, reference research when needed, targeted tests, and checkpoint after each successful chunk.
- Update ROADMAP.md and docs/PLANNING_REQUIREMENTS.md first; then reconcile the pre-R07 gate document so *offline blueprint* work is sequenced after the R04-R06 data/math prerequisites, but before Semi-Autonomous physical construction.
- This document does not authorize starting the game, changing saves, editing live services, loosening access controls or bypassing safety gates. GitHub publication requires its own explicit user authorization.