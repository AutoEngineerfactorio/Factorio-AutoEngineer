# R04-R06 data/math prerequisites for Phase 1B — 2026-10-19

**Status: IN PROGRESS.** R07 Helper authoring/library/preview is sequenced after the
entry criteria below; blueprint placement remains prohibited in Helper and belongs
to later gameplay work. Offline green tests are not live gameplay acceptance.

**Runtime targets:** Factorio 2.1.22 primary; Factorio 2.0.77 backport. The Python
source profile gate accepts only these exact versions with the qualified base-only
content set. That enables bounded read-only preview in offline/source tests; it is
not a claim that either installed game/backend pair has passed live acceptance.

## Implemented locally on main

- Read-only existing policy-8 display path: dashboard_feed.py accepts only a tightly bounded optional same-tick capability payload; autoengineer_dashboard.py shows actual read-only planning readiness instead of inventing recipes. The paged catalog adapter is in local backend source/patch, and the Python observer now assembles pages only when tick, version, force, surface, research, enabled content and source fingerprint match. The validated installed backend has not been rebuilt with it, so catalog metadata remains unavailable in validated runs.
- R05 observation mapping in read_only_planning.py covers bounded actually observed position, tick, surface and main inventory, with truncation state; does not infer permission, test success or verified actions.
- R04 optional capability envelope validates 2.x version label, force, research list, enabled first-party content, recipe category, ingredients/products, exact tick/surface and size. The read-only source-profile gate lists exact versions 2.1.22 and 2.0.77; neither is live-accepted by this change. Recipe categories come from the active force recipe view, so they support recipe grouping but do **not** claim a machine-to-category compatibility matrix. The backend adapter source computes a fingerprint over recipe/mod/research data; it is a change detector, not authentication. Unknown probabilities, quality, temperatures or other recipe fields are rejected, not simplified silently. Adapter behavior is not yet verified in rebuilt installed backends or either live game.
- Read-only recipe preview requires an exact allowed base-only source and externally observed machine crafting speed, actual machine power, continuous input rates in items/second (not inventory on hand), and power budget. Complex recipes are unsupported until their math is proven.
- The dashboard source now has a read-only recipe/research browser for observed recipe inputs/products (including fluids), enabled/hidden state, category/time, researched technologies and bounded technology recipe-unlock effects. Effects do not establish prerequisites or buildability. A bounded material-requirements preview expands selected item/fluid outputs through enabled recipes, reports ambiguity, cycles, unresolved inputs and uncredited co-products, and does not infer machine/rate/power/buildability. Offline tests cover representative item/fluid paths, shared inputs and multi-output accounting; the installed Windows UI and live backend remain unverified. Source-level production/power flow telemetry, local graphs and cautious bottleneck candidates are now implemented. Machine compatibility, general production feasibility, and live telemetry/runtime validation remain open.
- R05 telemetry is read-only and bounded: it samples 60 two-second flow values for up to four item and two fluid prototypes from rotating 128-item/64-fluid buckets; it samples up to eight visible own-force electric networks from at most 128 nearby poles. Flow rates are units/minute; electric API values remain joules/tick and the dashboard derives watts at 60 ticks/second. Partial coverage, unavailable data and stalled game ticks are surfaced. Recommendations identify only qualifying observed flow imbalances or low power satisfaction and are explicitly candidates, not diagnoses. No new game-write capability was added. Source/API compatibility is not live acceptance; the restricted backend must be rebuilt and checked in both Factorio 2.1.22 and 2.0.77 before runtime support is claimed.
- A persistent read-only freshness gate disables planning after 5 seconds without game tick progress, upon disconnect, or on regressed tick/clock. No new game write tool or permission was added.
- Older safe_executor.py direct --execute CLI is now disabled *before connecting to MCP*; approved movement remains the supervised Semi-Autonomous path.
- An offline 300-gears/minute fixture in r06_fixture_chain.py calculates 5 gears/s consuming 10 iron plates/s and 10 iron ore/s, requiring 4 assembling machines 2 and 16 electric furnaces without modules, beacons, downtime or logistical constraints. Estimated average draw from these machines is 3,496kW including idle drain, excluding belts, inserters and other equipment. It is an **offline calculation, not an actual built or measured factory**. ProductionSolver.get_fixture_proof links to this calculation.

## Official references for simple fixture

- https://wiki.factorio.com/Iron_gear_wheel — one gear from two iron plates in 0.5 s.
- https://wiki.factorio.com/Iron_plate — one iron plate from one ore in 3.2 s.
- https://wiki.factorio.com/Assembling_machine_2 — crafting speed 0.75, 150 kW active, 5 kW drain.
- https://wiki.factorio.com/Electric_furnace — crafting speed 2, 180 kW active, 6 kW drain.
- https://lua-api.factorio.com/latest/classes/LuaForce.html — force-owned recipes and technology.
- https://lua-api.factorio.com/latest/classes/LuaRecipe.html — enabled recipes, ingredients and products.
- https://lua-api.factorio.com/2.0.77/classes/LuaRecipe.html and https://lua-api.factorio.com/2.1.22/classes/LuaRecipe.html — versioned recipe runtime API references; documentation is not installed-runtime evidence.
- https://lua-api.factorio.com/2.0.77/classes/LuaEntityPrototype.html and https://lua-api.factorio.com/2.1.22/classes/LuaEntityPrototype.html — versioned prototype references; compatible machine/category mappings are not currently emitted.
- https://lua-api.factorio.com/latest/concepts/Ingredient.html — types and fluid/quality complexity.
- The restricted backend must be rebuilt and the adapter exercised against each exact installed game version before runtime support is claimed.

## Remaining mandatory work before R07 acceptance

### Phase 1B entry criteria for offline R07 codec/library/preview

These prerequisites establish trustworthy inputs to a local, non-gameplay blueprint
workflow; they do not certify all-product gameplay, H1, or placement.

1. Build and test the bounded read-only recipe/research adapter in pinned backend source AND reproducible combined backend-safety.patch. It is integrated into existing `autoengineer_view`; keep the exact 12-tool policy-v8 boundary. Do not enable arbitrary Lua/RCON or expand gameplay permissions. Test build, compatibility, payload caps, paging, disabled/hidden/unavailable recipes, exact force/surface, fog/private state and patch reconstruction.
2. Source-level paging (1..32 entries per request, 10,000-entry fail-closed cap) and a stable change-detection fingerprint are implemented. Offline Python assembly requires matching tick, version, force, surface, research, enabled content, fingerprint, page counts and ordering; research/content equality is compared directly rather than inferred only from the non-authenticating fingerprint. Incomplete catalogs fail closed for planning. Tests cover mixed snapshots, malformed counts, timeouts and truncation. Same-tick feasibility, latency, version compatibility and fingerprint behavior remain unverified against the rebuilt backend and live runtime. The fingerprint is not an authentication mechanism.
3. A source-level, bounded material-requirements path now covers representative item and fluid outputs, shared inputs and deterministic multi-output reporting. It does not credit co-products, optimize alternatives, or establish rates or feasibility. Cycles are unsupported; ambiguous recipes require explicit choices; disabled/hidden candidates and missing external inputs remain unresolved rather than being called non-producible. This offline evidence does not claim full R06 or live acceptance.
4. Keep current versus future buildability distinct. The source must preserve exact profile, force, surface, recipe/research provenance and missing/unsupported requirements. Machine compatibility and transport requirements may be reported only where observed/validated; otherwise the preview must mark them unknown, never assume them.

### Remaining work before full R07/H1 acceptance

1. R06 still needs net multi-product flow balance and co-product credit, alternatives optimization, machines/throughput, returned catalysts/recycling, quality and stochastic yields, fluid temperatures, module/beacon effects, resource/power/logistics constraints and per-output observed rates. The material preview is not a production-feasibility solver. The catalog does not yet identify compatible machine prototypes or their observed availability.
2. Validate Factorio 2.1.22 primary and 2.0.77 backport separately against the installed runtime, pinned FactorioMCP backend and restricted patch. Qualify Space Age, Quality and Elevated Rails individually in isolated first-party profiles; other 2.x patch versions remain unqualified. Third-party mod adaptation remains R20 last, with read-only discovery separately gated by 1C.
3. Perform explicit user-approved isolated live read-only verification, then only after H1 and separate authorization, supervised gameplay regression and measured 1/5/10-minute physical-factory runs with negative cases. Do not alter saves or operate Factorio without authorization.
4. Revalidate legacy CLI denial in the packaged Windows launcher and installed policy-v8 backend before claiming all R01 legacy paths closed.

## Current acceptance status

| Item | Offline evidence | Live acceptance |
|---|---|---|
| R01 legacy direct CLI | Disabled and unit-tested | Retest packaged backend |
| Factorio 2.1.22 primary / 2.0.77 backport | Exact-version source gate and offline parser/planner tests; backend adapter uses runtime-reported base version | BLOCKED: FactorioMCP checkout and installed game runtimes unavailable here; build, patch reconstruction and live read-only regression required separately on both |
| R04/R05 display observation integration | Offline parser, bounded adapter source and fail-closed page assembler | PARTIAL: backend build/runtime and live page aggregation not verified |
| R04 version/research/recipe pages | Offline same-snapshot assembly tests; incomplete catalogs cannot enable planning | BLOCKED: rebuild and live compatibility/latency acceptance pending |
| R06 single-recipe rate estimate and material requirements | Test-backed one-recipe estimator plus bounded item/fluid material-path preview; ambiguous/cyclic/unsupported inputs fail closed | PARTIAL: rates, machine/power inputs and material paths are not live-verified; production flow solver remains unfinished |
| R06 300 gears/min physical factory | Source-backed fixture arithmetic | BLOCKED: no physical run |
| Base game future 2.x/Space Age/Quality/Elevated Rails | Explicit fail-closed tests | NOT YET QUALIFIED |
| R07 offline codec/library/preview | Not started; Phase 1B entry criteria above remain open | WAIT until R04–R06 data/math prerequisites pass; Helper placement prohibited |

All current work remains uncommitted on local main. No gameplay, save edits, GitHub publication, or model changes authorized by this document.
