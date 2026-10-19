# AutoEngineer decisions carried forward — October 19, 2026

This handoff records the user's current priorities for the existing project. It is a requirement and sequencing update, **not** evidence that a feature was implemented or live-tested. The canonical R01–R20 acceptance requirements and safety gates remain binding.

## The three modes and order of work

1. **AI Helper (read-only game interaction):** fully reliable mod-aware observations, a live dashboard and an accurate, deterministic production/blueprint planning assistant **first**. Selecting or exporting a local blueprint must not issue game-changing commands.
2. **Semi-Autonomous:** only after component-specific tests; human-approved bounded actions, re-observation and fail-closed Stop/takeover.
3. **Fully Autonomous:** stays visibly locked until all required acceptance gates pass; no unilateral expansion of permissions.

The binding delivery order is **R04 telemetry/data truth → Dashboard/R05/R06 deterministic AI Helper → pre-R07 data/math readiness → read-only Blueprint Studio (R07 and read-only R08) → version/provenance-checked design discovery → Gate H1 user signoff → expanded Semi-Autonomous R08–R16 → much later, independently qualified Full Autonomy**. Physical construction, real supply and verified production are gameplay requirements after H1; separately authorized pre-H1 human-built factory measurements may be required for H1 evidence. See [Helper-first details and measurable Gate H1](HELPER_FIRST_GATE_H1.md). This is prioritization, not a claim those features or the gate are complete.

## AI Helper: more capable than a Helmod-style calculator

Use the *actual loaded* game/profile version, recipe and technology unlocks, surfaces, machine capabilities, modules, items/fluids and research — not hardcoded vanilla formulas. The Helper must explain missing observations and never invent a recipe. A deterministic engine should solve alternate pathways, multi-output/byproducts and recycling, productivity and quality, fluids and temperatures, shortages, machine ratios, power, transport, belts, pipes, pumps, inserters, trains, logistics/construction bots and circuit constraints.

User-specified targets may range from small production lines to megafactories. Compare material, energy, construction and space costs and estimated throughput; surface whether those results are planned, simulated, observed or physically measured. Present a plan, item bill and production chain in the dashboard before creating a **local** blueprint proposal. After R07/R08 qualify, support blueprint libraries with provenance, versioning, verification and game-specific compatibility.

Allow optional online research of the Factorio wiki, mod portal, official API, mod authors, Reddit, blueprint-sharing websites and YouTube for user-approved blueprint/design references. Treat external designs as **untrusted references**, verify game/mod version, redistribution rights, license, actual research unlocks and performance; do not copy or auto-place arbitrary online blueprint strings.

## Dashboard and telemetry

Keep the live read-only game map, inventory, objectives, current research, production/power graphs, stalled factories, fluid/heat, bottlenecks, trains, robots, logistics and eventual combat overlays independent of any language model request. Distinguish source-observed fields from estimates; show staleness, gaps, thresholds and profile/version. Provide clear approval/deny, manual takeover, Stop, offline and error states. No background action can bypass policy.

Agent/Zoo Code/Copilot collaboration should use structured, bounded observation data plus replayable offline fixtures, issue/commit reviews and test reports rather than guesses. Changes should undergo deterministic unit tests, telemetry schema checks, source audits and explicit live test gates. A local watcher/verification loop may be developed later; it must be opt-in, rate-limited, and never assume authority to publish, modify saves or run Factorio unattended. Pillow/static screenshot tests may supplement UI validation, not replace live game acceptance.

## Version and modded-development strategy

Keep the currently qualified baseline pinned until an explicit backup, compatibility audit and regression suite justify changing it. A Factorio 2.1 experimental track may be tested separately; do not presume the current server/mod dependencies support it, update the active executable automatically or migrate saves.

Keep vanilla/Space Age, Space Exploration and Pyanodons in **separate mod/save/write-data profiles**. The full Pyanodons suite is the continuous *development benchmark* for recipe-graph scale, telemetry completeness, dashboard responsiveness, byproduct/cycle handling and AI Helper latency/memory. Begin with synthetic pY-shaped fixture tests now; use authentic mod data and live pY play only after versioned read-only adapters and safety qualification. See [continuous benchmarks](CONTINUOUS_MOD_BENCHMARKS.md). This does not mean pY has been installed, or that R20 modded gameplay acceptance has been achieved.

Optional time-acceleration/time-tools mods must never silently alter reproducible baseline test speed or invalidly inflate performance comparisons. Use isolated opt-in saves and record tick/UPS and configuration.

## Development evidence and next gates

- No release, test, API contract or project milestone is complete because this handoff says so.
- Keep the existing FactorioMCP fork/source, restricted backend policies, legal game mechanics, five-tile bounded development movement and human safety controls.
- R04/R05: establish authenticated, bounded, paginated live observations of game/mod/research/recipe state with freshness and provenance.
- R06: build and validate multi-product deterministic math, offline fixture cases and eventually isolated physical measurements at 1/5/10-minute windows.
- R07 read-only blueprint authoring stays blocked by the **narrow** [pre-R07 readiness](R04_R06_PRE_R07_ACCEPTANCE.md); its fidelity and safety are required for later [Gate H1](HELPER_FIRST_GATE_H1.md). Semi feature expansion is locked until H1, and Full Autonomy requires additional gates.

**Current change scope:** documentation, synthetic read-only benchmarks and tests. No remote game control, Factorio version upgrade, live pY installation, automatic Zoo Code watcher, blueprint placement or release were executed here.
