# AutoEngineer decisions carried forward — October 19, 2026

This handoff records the user's current priorities for the existing project. It is a requirement and sequencing update, **not** evidence that a feature was implemented or live-tested. The canonical R01–R20 acceptance requirements and safety gates remain binding.

The later [Helper-first roadmap amendment](../ROADMAP.md) supersedes the delivery order below where they differ; it does not change permission boundaries or acceptance evidence.

## The three modes and order of work

1. **AI Helper (read-only game interaction):** fully reliable mod-aware observations, a live dashboard and an accurate, deterministic production/blueprint planning assistant **first**. Selecting or exporting a local blueprint must not issue game-changing commands.
2. **Semi-Autonomous:** only after component-specific tests; human-approved bounded actions, re-observation and fail-closed Stop/takeover.
3. **Fully Autonomous:** stays visibly locked until all required acceptance gates pass; no unilateral expansion of permissions.

The current delivery order is **preserve/harden R01–R03 → Phase 1A Helper + Dashboard → Phase 1B non-gameplay Blueprint Studio → Phase 1C authorized read-only discovery → H1 acceptance → Phase 2 Semi-Autonomous**. Phase 3 Full Autonomy remains separately gated. Offline R07 codec/library/preview follows the specific R04–R06 data-truth and data/math prerequisites in the pre-R07 gate; R08/R09 gameplay construction remains later. This is a feature priority, not an assertion that any requirement is complete.

## AI Helper: more capable than a Helmod-style calculator

Use the *actual loaded* game/profile version, recipe and technology unlocks, surfaces, machine capabilities, modules, items/fluids and research — not hardcoded vanilla formulas. The Helper must explain missing observations and never invent a recipe. A deterministic engine should solve alternate pathways, multi-output/byproducts and recycling, productivity and quality, fluids and temperatures, shortages, machine ratios, power, transport, belts, pipes, pumps, inserters, trains, logistics/construction bots and circuit constraints.

User-specified targets may range from small production lines to megafactories. Compare material, energy, construction and space costs and estimated throughput; surface whether those results are planned, simulated, observed or physically measured. Present a plan, item bill and production chain in the dashboard before creating a **local** blueprint proposal. After R07/R08 qualify, support blueprint libraries with provenance, versioning, verification and game-specific compatibility.

Allow optional online research of the Factorio wiki, mod portal, official API, mod authors, Reddit, blueprint-sharing websites and YouTube for user-approved blueprint/design references. Treat external designs as **untrusted references**, verify game/mod version, redistribution rights, license, actual research unlocks and performance; do not copy or auto-place arbitrary online blueprint strings.

## Dashboard and telemetry

Keep the live read-only game map, inventory, objectives, current research, production/power graphs, stalled factories, fluid/heat, bottlenecks, trains, robots, logistics and eventual combat overlays independent of any language model request. Distinguish source-observed fields from estimates; show staleness, gaps, thresholds and profile/version. Provide clear approval/deny, manual takeover, Stop, offline and error states. No background action can bypass policy.

Agent/Zoo Code/Copilot collaboration should use structured, bounded observation data plus replayable offline fixtures, issue/commit reviews and test reports rather than guesses. Changes should undergo deterministic unit tests, telemetry schema checks, source audits and explicit live test gates. A local watcher/verification loop may be developed later; it must be opt-in, rate-limited, and never assume authority to publish, modify saves or run Factorio unattended. Pillow/static screenshot tests may supplement UI validation, not replace live game acceptance.

## Version and modded-development strategy

The current implementation targets Factorio **2.1.22** as primary and keeps
**2.0.77** as a separate backport target. Maintain isolated profiles, mod
directories and disposable saves for both. Source compatibility gates and offline
tests do not establish runtime/backend compatibility: build the restricted backend
against its pinned upstream, rebuild the patch cleanly, and run the read-only
acceptance suite on each exact runtime before claiming support. Never auto-update an
executable or migrate saves between versions.

Keep vanilla/Space Age, Space Exploration and Pyanodons in **separate mod/save/write-data profiles**. The full Pyanodons suite is the continuous *development benchmark* for recipe-graph scale, telemetry completeness, dashboard responsiveness, byproduct/cycle handling and AI Helper latency/memory. Begin with synthetic pY-shaped fixture tests now; use authentic mod data and live pY play only after versioned read-only adapters and safety qualification. See [continuous benchmarks](CONTINUOUS_MOD_BENCHMARKS.md). This does not mean pY has been installed, or that R20 modded gameplay acceptance has been achieved.

Optional time-acceleration/time-tools mods must never silently alter reproducible baseline test speed or invalidly inflate performance comparisons. Use isolated opt-in saves and record tick/UPS and configuration.

## Development evidence and next gates

- No release, test, API contract or project milestone is complete because this handoff says so.
- Keep the existing FactorioMCP fork/source, restricted backend policies, legal game mechanics, five-tile bounded development movement and human safety controls.
- R04/R05: establish authenticated, bounded, paginated live observations of game/mod/research/recipe state with freshness and provenance.
- R06: build and validate multi-product deterministic math, offline fixture cases and eventually isolated physical measurements at 1/5/10-minute windows.
- R07 offline authoring/library/preview may start only after the specific [pre-R07 data/math prerequisites](R04_R06_PRE_R07_ACCEPTANCE.md) pass; Helper placement remains prohibited. Semi-Autonomous gameplay waits for H1, and Full Autonomy remains separately gated.

**Scope recorded for this handoff:** documentation, synthetic read-only benchmarks and tests. No remote game control, Factorio version upgrade, live pY installation, automatic Zoo Code watcher, blueprint placement or release were executed here. Later work still requires explicit authorization for any live game/save operation, publication or automation.
