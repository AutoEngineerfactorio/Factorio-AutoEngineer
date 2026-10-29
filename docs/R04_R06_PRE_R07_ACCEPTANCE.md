# R04-R06 data/math prerequisites for Phase 1B — 2026-10-19

**Current verification:** see [October 28 Helper development status](HELPER_DEVELOPMENT_STATUS_2026-10-28.md). Older entries below are historical; the current Gate H1 remains open.

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
| R06 stochastic production model | `plan_stochastic_recipe` keeps the guaranteed output, the justified expectation and the bounds apart; byproducts carry the same three quantities; a ranged output reports no expectation; `ignored_by_productivity` is applied as the game's own deduction. 12 offline regressions in `tests/test_read_only_planning.py` | NOT LIVE-VERIFIED: the backend fix that preserves the observed probability is source-only, so no live recipe has been planned from a real probability yet |
| R06 machine compatibility | The observed machine report carries the crafting categories, crafting speed, energy usage, module slots, the allowed effects, the allowed module categories and the declared fluid-box fields. The effect names and the fluid-box production types are the closed 2.1.23 literal unions | NOT LIVE-VERIFIED: the deployed backend still reports the invented fluid-box field names |
| R06 read-only blueprint planning model | `plan_blueprint` determines the machines that can craft a recipe, the machine count and its basis, the input and output throughput, the power, the byproducts, the unlock technologies and the alternative machine configurations. 10 offline regressions | READY FOR THE OFFLINE R07 ENTRY GATE as a planning model only; it places nothing and writes nothing, and its inputs still need a live-verified catalog |
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

## Live read-only MODDED (Pyanodons) catalog verification — 2026-10-26

Evidence kind: LIVE READ-ONLY against the disposable modded profile
`.local/launcher-profiles/2.1.23` with the modded save
`autoengineer-test modded.zip` and the mod sources in
`.local/mod-test-mods/2.1.23`. The save digest was compared before and
after and is unchanged. No gameplay write, research change, item grant or
save modification was performed.

Machine-readable report:
`.local/live-pillow-2.1.23/evidence/modded-live-005.json`.

### A large modpack defect, found live and fixed

The first modded run (`modded-live-004`) returned
`catalog_status: "catalog_limit"` with **zero** recipes, even though the
server had loaded all 20 mods and a client was connected.

Cause: the adapter's recipe-name list is the paging index, and the
collection helper returned `nil` when the count exceeded 10,000, which
failed the whole catalog. The Pyanodons suite alone carries more than
10,000 recipes, so the entire modded catalog was unusable.

Fix: the name list is collected in full and pages over the real index; an
overflow is reported through the existing `truncated` marker instead of
abandoning the catalog. The Python entry caps
(`MAX_CATALOG_ENTRIES`, `MAX_RECIPE_CATALOG_ROWS`) are now derived from the
backend's own page range instead of a flat 10,000-entry cap. No tool was
added and the per-page bounds are unchanged.

### Verified after the fix (`modded-live-005`)

| item | value |
| --- | --- |
| `catalog_status` | `ok` |
| recipes declared | **10146** |
| pages | **635** at page size 16 |
| pages fetched | **635 / 635**, 0 errors |
| duplicate recipe names | 0 |
| global ordering | sorted |
| rows returned | 7807 of 10146 (the rest use unsupported advanced mechanics; `truncated` is reported `true`) |
| modded recipes observed | 209, e.g. `py-aluminium`, `cybersyn-combinator`, `py-biomass-powerplant-mk01` |
| force / surface | `player` / `nauvis` |
| game version | 2.1.23 |
| enabled content | 30 mods, including 9 Pyanodons mods |
| researched technologies observed | 1 (`hidden-mining-fluid-autounlock`) |
| fingerprint / force / surface / version / research / content | one single value across all pages |
| latency per page | min 2.109 s, mean 2.140 s, max 2.672 s |
| page sizes 1 / 2 / 32 | served; `total_pages` 10146 / 5073 / 318 |
| page 0, page 10001, page 99999, size 0, size 33 | all rejected |
| policy | `{"version":8,"max_walk":5,"restricted":true,"mode":"helper"}` |
| tools called | `autoengineer_view` and `autoengineer_policy` only |
| server log errors | 0 |
| modded save SHA-256 before / after | `477a440783c75f65ace91a96f41926129ac4c6d48d254527eb59d061b9ba1c78` / identical |

Modded rows carry the shapes the planner needs and the earlier view-model
defects covered: a **fluid** ingredient (`acidgas`, 100 units) on
`3-diethylaminophenol`, an **unresearched** technology unlock
(`intermetallics-mk03`), a **hidden** recipe
(`1d-photonic-crystal-pyvoid`), a **non-deterministic** product (`ash`) and
**multi-category** rows (`py-incineration`, `chemistry`).

### Still open after this run

1. 7,807 of 10,146 recipes are exposed; the remainder use advanced
   mechanics the bounded adapter does not model. Closing that gap is the
   open R06 mechanics work.
2. The **same-tick whole-catalog** limit stands: the 635-page sweep spans
   many ticks, so the same-tick assembler correctly refuses to present it
   as one snapshot. The page-scoped contract is the working path for a
   modded profile.
3. `source_fingerprint` is `null` on the modded profile because the
   fingerprint's 2 MB / 100,000-node budget is exceeded. A modded profile
   therefore has no change detector; a streaming per-page fingerprint is the
   follow-up.

### Resolved after this run

4. The restricted backend exposes **13** tools. The *enforced* boundary was
   never 12: `backend-safety/AutoEngineerTools.cs` carries exactly 13
   entries in its `Allowed` allowlist (9 tools in `AutoEngineerTools` plus 4
   in `SafetyTools`), and
   `tests/test_backend_adapter_contract.py::test_the_restricted_tool_boundary_is_unchanged`
   asserts 13 distinct names and requires `autoengineer_telemetry` to be
   present. The "12-tool" figure in the prose was a stale count from before
   the telemetry tool was added. The allowlist, the dispatch filter and the
   policy-v8 boundary are unchanged; only the prose is corrected. No tool was
   removed and no capability was widened.
5. A refused recipe is no longer dropped **silently**. The adapter now
   reports each dropped recipe with the reason that was observed
   (`unknown_field:<field>`, `no_products`, `ingredient_shape:<field>`,
   `product_shape:<field>`, `no_category`, `bad_crafting_time`, or
   `unclassified` when the cause cannot be proven). The gap between the
   declared recipe total and the emitted rows can therefore be *classified*
   instead of only counted. The reason vocabulary is:

   | reason | the observed cause |
   | --- | --- |
   | `unknown_field:<field>` | a part carries a field the adapter does not accept |
   | `no_products` | the recipe declares no product |
   | `ingredient_shape:<field>` | an ingredient is missing a name, a type or a positive amount |
   | `product_shape:<field>` | a product is missing a name, a type or has a bad amount |
   | `no_category` | the recipe declares no usable crafting category |
   | `bad_crafting_time` | the crafting time is missing, non-numeric or not above zero |
   | `unclassified` | the cause could not be proven from the observed prototype |

   The Python side validates the report and refuses a malformed one:
   `read_only_planning.validate_exclusions` and
   `read_only_planning.classify_exclusions`.
6. The catalog now carries the game's **crafting machines**. Each machine is
   read from the game's own entity prototypes and reports the crafting
   categories it can run, its crafting speed, its energy usage and its
   module slots. Vanilla, Space Age and modded machines are all covered
   without naming any of them, and a machine whose speed or energy the game
   does not expose is refused rather than given a default.

### Measured state of the observed Pyanodons catalog

From the captured live run (`r06-final-int-b`, 30 enabled mods, 10,146
declared recipes, 9,467 emitted rows), measured with
`tests/r06_catalog_perf_benchmark.py`:

| observation | count | meaning |
| --- | --- | --- |
| `disabled` | 6,827 | the recipe is disabled in the observed game data |
| `stochastic_product` | 2,624 | the product has a probability-based yield |
| **plannable by the simple path** | **16** | enabled, one deterministic item product |

So the dominant blueprint-generation blocker is **not** the 679 excluded
recipe names. It is that the observed catalog is mostly research-locked, and
that a further 2,624 recipes have a probabilistic yield that the fixed-rate
path refuses. The probabilistic-yield path is the next R06 mechanics work.

### Correction to the `stochastic_product` attribution — 2026-10-27

Re-reading the **captured** catalog rows (`r06-final-int-b-catalog-rows.json`)
offline corrected the meaning of the `stochastic_product` row above. The
count of 2,624 is real, but the *cause* was not proven by that evidence:

| measured fact about the captured rows | value |
| --- | --- |
| emitted rows | 9,467 (2,640 enabled, 6,827 disabled) |
| enabled recipes in the `py-incineration` category | **2,623** |
| enabled recipes with more than one product | **0** |
| products carrying `independent_probability` | **0** |
| products carrying `shared_probability` | **0** |
| products carrying `amount_min` / `amount_max` | **0** |
| products carrying `extra_count_fraction` | **0** |
| products carrying `ignored_by_productivity` | **0** |
| products carrying `deterministic: false` with **no** probability field | **2,624** |
| enabled recipes with an unlock technology | **0** |

The 2,624 rows were therefore marked non-deterministic **without any
probability value in the captured data**. The backend adapter that produced
that capture validated `independent_probability` and `shared_probability`
but never wrote either field into the reported row, so the probability was
observed and then discarded. The captured evidence therefore proves that a
sub-certain product existed, but it does **not** prove a probability-based
yield for those recipes.

Two defects were found and fixed offline in this phase:

1. **The observed probability was discarded.** The adapter now writes
   `independent_probability`, `shared_probability` and `affected_by_quality`
   into the reported row. The 2.1.23 prototype API confirms
   `ProductPrototypeBase` declares `independent_probability` as a double and
   `shared_probability` as a `SharedProbabilityDefinition`.
2. **The fluid box reported invented field names.** The adapter read
   `box.filter_type` and `box.fluid_box_index`, but the 2.1.23 `FluidBox`
   declares `production_type`, `filter` and `volume` and declares neither of
   those names, so the reported filter was always the literal fallback
   `"item"`. The adapter now reads the declared fields.

Both fixes are source-level and are covered by regression tests that run the
real adapter Lua. **They are not yet live-verified**: the deployed backend
and the installed 2.1.23 runtime still carry the old behaviour, so the
2,624 recipes remain unclassifiable until a live read-only run against a
rebuilt backend captures the per-recipe reasons.

### The stochastic production model — implemented offline 2026-10-27

`read_only_planning.plan_stochastic_recipe` plans a recipe whose output may
be probabilistic or ranged, and keeps three quantities apart:

| quantity | when it is reported |
| --- | --- |
| `guaranteed_per_second` | only when the observed mechanics make the amount certain |
| `expected_per_second` | only when the observed probability justifies it |
| `minimum_per_second` / `maximum_per_second` | always kept for a ranged or probabilistic output |

The expectation is reported only where it is a real expectation and not a
guess:

* `independent_probability` is a per-craft probability, so the expected
  units per craft are `probability * amount`; that is reported.
* `extra_count_fraction` is the probability of one extra unit, so its
  contribution is `fraction`; that is reported.
* a product whose amount is a **range** has no verified distribution inside
  the range in Factorio 2.1.23, so its expectation stays **unknown** rather
  than being guessed as the midpoint.
* a **shared** probability is a `{min,max}` definition and the roll is
  shared between the products, so only the per-product width is reported and
  the joint expectation of the recipe is not asserted.

Byproducts are reported with the same three quantities, so a caller can
tell a guaranteed byproduct from an occasional one. A productivity bonus is
applied only to the part of the output the game says responds to it:
`ignored_by_productivity` is the amount deducted from a productivity-induced
bonus craft.

### The read-only blueprint planning model — implemented offline 2026-10-27

`read_only_planning.plan_blueprint` connects the verified production result
to a planning model. It answers, from the observed catalog and the observed
machines only:

* which machines can craft the recipe, and for each one its crafting speed,
  module slots, allowed effects, allowed module categories and fluid boxes;
* how many machines are required, and on which basis (guaranteed or
  expected);
* the input and output throughput per second and per minute;
* the power requirement in kilowatts;
* the byproducts and their throughput, so they can be routed;
* the unlock technologies with the researched flag the game reports;
* the alternative machine configurations, one per observed machine.

Nothing in this model places a blueprint or writes to the game. A recipe
the observed data cannot plan is reported as `unresolved` with a reason.

### Measured performance

`tests/r06_catalog_perf_benchmark.py`, same machine, same workload:

| input | recipes | validate | model build | search | plan | peak memory |
| --- | --- | --- | --- | --- | --- | --- |
| SYNTHETIC-1000 | 1,000 | 0.106 s | 0.008 s | 0.00006 s | 0.0003 s | 1.55 MB |
| SYNTHETIC-5000 | 5,000 | 0.567 s | 0.041 s | 0.00027 s | 0.0004 s | 7.59 MB |
| SYNTHETIC-10000 | 10,000 | 1.126 s | 0.081 s | 0.00053 s | 0.0004 s | 15.13 MB |
| **OBSERVED-PYANODONS** | **9,467** | **1.383 s** | **0.081 s** | **0.00068 s** | **0.00045 s** | **17.30 MB** |

The SYNTHETIC rows are synthetic fixtures with the *shape* of a large
modpack; they are not Pyanodons recipe data. The OBSERVED row uses the real
captured recipe rows; the machines paired with them are still synthetic,
because the captured evidence predates the machine report.

Ordinary telemetry polling never performs a full sweep: the observer
requests **one** catalog page per cycle, and the multi-page sweep needs an
explicit `catalog_only` + `full_catalog` request that is never retried
automatically. The catalog model is built on a worker thread and applied on
the UI thread, and the recipe search scans every row while the tree view
inserts only a bounded number of rows.
