# R04-R06 data/math prerequisites for Phase 1B — 2026-10-19

**Status: IN PROGRESS.** R07 Helper authoring/library/preview is sequenced after the
entry criteria below; blueprint placement remains prohibited in Helper and belongs
to later gameplay work. Offline green tests are not live gameplay acceptance.

**Current target:** Factorio **2.1.23** only. 2.1.22 and 2.0.77 are archived/rollback,
not active regression targets. The Python source profile gate recognizes exactly
**2.1.23** with the qualified base-only content set. That enables bounded read-only
preview in offline/source tests; it is not installed runtime acceptance.

## Implemented locally on main

- Read-only existing policy-8 display path: dashboard_feed.py accepts only a tightly bounded optional same-tick capability payload; autoengineer_dashboard.py shows actual read-only planning readiness instead of inventing recipes. The paged catalog adapter is in local backend source/patch, and the Python observer now assembles pages only when tick, version, force, surface, research, enabled content and source fingerprint match. On 2026-10-20 the combined patch applied to the clean pinned FactorioMCP revision and built successfully in an isolated offline Release build with zero warnings/errors. The installed backend and live 2.1.23 catalog path remain unverified.
- R05 observation mapping in read_only_planning.py covers bounded actually observed position, tick, surface and main inventory, with truncation state; does not infer permission, test success or verified actions.
- R04 optional capability envelope validates 2.x version label, force, research list, enabled first-party content, recipe category, ingredients/products, exact tick/surface and size. The read-only source-profile gate lists the exact version 2.1.23; source qualification is not live acceptance. Recipe categories come from the active force recipe view, so they support recipe grouping but do **not** claim a machine-to-category compatibility matrix. The backend adapter source computes a fingerprint over recipe/mod/research data; it is a change detector, not authentication. Unknown probabilities, quality, temperatures or other recipe fields are rejected, not simplified silently. Adapter behavior is not yet verified in the installed backend or live 2.1.23 game.
- Read-only recipe preview requires an exact allowed base-only source and externally observed machine crafting speed, actual machine power, continuous input rates in items/second (not inventory on hand), and power budget. Complex recipes are unsupported until their math is proven.
- The dashboard source now has a read-only recipe/research browser for observed recipe inputs/products (including fluids), enabled/hidden state, category/time, researched technologies and bounded technology recipe-unlock effects. Effects do not establish prerequisites or buildability. A bounded material-requirements preview expands selected item/fluid outputs through enabled recipes, reports ambiguity, cycles, unresolved inputs and uncredited co-products, and does not infer machine/rate/power/buildability. Offline tests cover representative item/fluid paths, shared inputs and multi-output accounting; the installed Windows UI and live backend remain unverified. Source-level production/power flow telemetry, local graphs and cautious bottleneck candidates are now implemented. Machine compatibility, general production feasibility, and live telemetry/runtime validation remain open.
- R05 telemetry is read-only and bounded: it scans at most 10,000 item/fluid prototype names and returns 60 two-second flow values for at most 16 active item and eight active fluid series; it samples up to eight visible own-force electric networks from at most 128 nearby poles. Flow rates are units/minute; electric API values remain joules/tick and the dashboard derives watts at 60 ticks/second. Partial coverage, unavailable data and stalled game ticks are surfaced. Recommendations identify only qualifying observed flow imbalances or low power satisfaction and are explicitly candidates, not diagnoses. No new game-write capability was added. The declared telemetry suite passed live on historical 2.1.22; 2.1.23 installed-runtime acceptance remains required.
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
- https://lua-api.factorio.com/2.1.23/classes/LuaRecipe.html — active-target recipe runtime API reference; documentation is not installed-runtime evidence.
- https://lua-api.factorio.com/2.1.23/classes/LuaEntityPrototype.html — active-target prototype reference; compatible machine/category mappings are not currently emitted.
- https://lua-api.factorio.com/latest/concepts/Ingredient.html — types and fluid/quality complexity.
- The restricted patch builds against the pinned backend; the adapter must still be exercised against the exact installed 2.1.23 runtime before support is claimed.

## Remaining mandatory work before R07 acceptance

### Phase 1B entry criteria for offline R07 codec/library/preview

These prerequisites establish trustworthy inputs to a local, non-gameplay blueprint
workflow; they do not certify all-product gameplay, H1, or placement.

1. The bounded read-only recipe/research adapter is present in readable source and the reproducible combined backend-safety.patch. The patch applies to the clean pinned backend and its isolated offline Release build passes. It is integrated into existing `autoengineer_view`; keep the exact 12-tool policy-v8 boundary. Do not enable arbitrary Lua/RCON or expand gameplay permissions. Live 2.1.23 compatibility, paging, force/surface and fog/private-state behavior remain required.
2. Source-level paging (1..32 entries per request, 10,000-entry fail-closed cap) and a stable change-detection fingerprint are implemented. Offline Python assembly requires matching tick, version, force, surface, research, enabled content, fingerprint, page counts and ordering; research/content equality is compared directly rather than inferred only from the non-authenticating fingerprint. Incomplete catalogs fail closed for planning. Tests cover mixed snapshots, malformed counts, timeouts and truncation. Same-tick feasibility, latency, version compatibility and fingerprint behavior remain unverified against the rebuilt backend and live runtime. The fingerprint is not an authentication mechanism.
3. A source-level, bounded material-requirements path now covers representative item and fluid outputs, shared inputs and deterministic multi-output reporting. It returns validated game/source fingerprint, force, surface, tick, content/research provenance, selected per-craft recipe details, structured ambiguity/unlock limitations and uncertainty. It does not credit co-products, optimize alternatives, or establish throughput or physical buildability. Cycles are unsupported; ambiguous recipes require explicit choices; disabled/hidden candidates and missing external inputs remain unresolved rather than being called non-producible. This offline evidence does not claim full R06 or live acceptance.
4. Keep current versus future buildability distinct. The source must preserve exact profile, force, surface, recipe/research provenance and missing/unsupported requirements. Machine compatibility and transport requirements may be reported only where observed/validated; otherwise the preview must mark them unknown, never assume them.

### Remaining work before full R07/H1 acceptance

1. R06 now has an independently exercised bounded deterministic acyclic material-flow calculation with external co-product credit and explicit unsupported results for several advanced mechanics. `Recipe.base_speed` remains items/second; absolute-quantity flow uses separately validated output-per-craft data and fails closed when that data is absent. Optional craft duration and energy-per-craft fields distinguish time, power in kW and energy in kJ; an absolute quantity without a production duration cannot establish power feasibility. Alternatives optimization, intermediate co-product balance, returned catalysts/recycling, quality and stochastic yields, fluid temperatures, module/beacon effects, resource/power/logistics constraints and per-output observed rates remain open. The bounded catalog material preview remains the safe preliminary bill interface; neither interface is a production-feasibility proof.
2. Validate Factorio 2.1.23 against the installed runtime (previous version results are archived, not transferable), pinned FactorioMCP backend and restricted patch. Qualify Space Age, Quality and Elevated Rails individually in isolated first-party profiles; other 2.x patch versions remain unqualified. Third-party mod adaptation remains R20 last, with read-only discovery separately gated by 1C.
3. Perform explicit user-approved isolated live read-only verification, then only after H1 and separate authorization, supervised gameplay regression and measured 1/5/10-minute physical-factory runs with negative cases. Do not alter saves or operate Factorio without authorization.
4. Revalidate legacy CLI denial in the packaged Windows launcher and installed policy-v8 backend before claiming all R01 legacy paths closed.

## Current acceptance status

| Item | Offline evidence | Live acceptance |
|---|---|---|
| R01 legacy direct CLI | Disabled and unit-tested | Retest packaged backend |
| Factorio 2.1.23 active / older profiles archived | Exact-version source gate, offline parser/planner tests, patch reconstruction and clean pinned isolated backend build | PASS — live read-only qualification completed on the isolated disposable 2.1.23 profile |
| R04/R05 display observation integration | Offline parser, bounded adapter source, fail-closed page assembler and isolated backend build | PASS — live `autoengineer_view` returns the bounded catalog, terrain, inventory and telemetry |
| R04 version/research/recipe pages | Offline same-snapshot assembly tests; incomplete catalogs cannot enable planning | PARTIAL — live paging, fingerprint, ordering, bounds and latency verified; a same-tick whole-catalog read is still blocked by the running game clock |
| R06 rate estimate and material requirements | Test-backed one-recipe estimator; source-identified item/fluid preliminary bill; deterministic acyclic quantity flow uses explicit per-craft yield and kJ energy, preserves items/second rate semantics, and fails closed without yield data | PARTIAL: advanced mechanics, power feasibility without duration, observed rates, physical buildability and live material paths remain unverified |
| R06 300 gears/min physical factory | Source-backed fixture arithmetic | BLOCKED: no physical run |
| Base game future 2.x/Space Age/Quality/Elevated Rails | Explicit fail-closed tests | NOT YET QUALIFIED |
| R07 offline codec/library/preview | Not started; Phase 1B entry criteria above remain open | READY for the offline R07 entry gate; Helper placement prohibited |

## Live read-only 2.1.23 catalog qualification — verified 2026-10-24

Evidence kind: LIVE READ-ONLY against the isolated disposable profile
`.local/live-pillow-2.1.23`. The launcher profile save digest was compared
before and after every run and is unchanged. No gameplay write, research
change, world change, placement or save modification was performed.

- Factorio **2.1.23 (build 87750, win64, full)**; base, space-age, quality,
  elevated-rails and autoengineer-input 2.1.23 all loaded.
- The restricted backend exposes **exactly 12 tools** and reports policy
  `{"version":8,"max_walk":5,"restricted":true,"mode":"helper"}`.
- Identity: force `player`, surface `nauvis`, 662 recipes, 42 pages at page
  size 16, fingerprint `poly31x131-v1:...`, enabled content
  `[autoengineer-input, base, elevated-rails, quality, recycler, space-age]`.
- Paging: 42/42 pages fetched, no transport error, no duplicate names,
  globally deterministic ordering, and one single fingerprint/force/surface/
  version/research/content set across all pages.
- Latency: 0.406 s minimum, 0.408 s mean, 0.422 s maximum per page.
- Bounds: page sizes 1, 2 and 32 are served; page 0, page 10001, page 99999,
  size 0 and size 33 are rejected.
- Freshness: the tick advances between observations and the catalog tick always
  equals the view tick.
- Telemetry: production `ok`; power `unavailable` because no visible own-force
  electric network exists in the disposable save.

Two demonstrated integration defects were found and corrected.

1. **Factorio 2.1.23 console-command confirmation gate.** The first console
   command of a fresh server is held pending and only an identical repeat
   executes it, so the first `autoengineer_view` returned an empty payload. The
   corrected backend pre-clears the gate once per connection with a read-only
   probe sent twice. No gameplay command is repeated, so no write is applied
   twice.
2. **Factorio 2.1 recipe and ingredient field shapes.** Every 2.1.23 product
   carries `affected_by_quality`, `independent_probability` and
   `shared_probability`, and several ingredients carry `ignored_by_stats`,
   `spoil_weight` or fluid-box hints. The strict adapter rejected every row.
   The adapter now accepts exactly those bounded fields, accepts a zero-amount
   product, keeps multi-category recipes with a bounded category list, marks a
   sub-certain product as non-deterministic and still rejects every unknown
   field. **312 of 662 recipes are exposed**; the remaining recipes use
   unsupported advanced mechanics and correctly fail closed with a truncation
   marker.

### Known architectural limit: same-tick whole-catalog assembly

The live Python assembler fails closed with *"Recipe catalog changed during
page assembly"*. The game runs at 60 UPS, so the tick advances during the
roughly 17 second 42-page sweep; a catalog read across different ticks is not
one consistent snapshot and must not be presented as one. Raising timeouts
cannot fix this. Resolving it needs an architectural change, for example a
single-request whole-catalog read, a fixed-tick observation window, or an
explicit per-page-tick snapshot contract. Until then the R07 codec must not
depend on a live assembled catalog and must use offline fixtures or a
single-page qualified catalog.

This file is a planning and evidence register. Its source/patch tests do not themselves prove installation, Factorio gameplay, save updates, a public release, or Gate H1 acceptance. Publication of this document does not authorize live services, game actions, or model changes.
