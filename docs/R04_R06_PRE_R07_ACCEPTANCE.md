# R04-R06 pre-R07 acceptance gate — 2026-10-18

**Status: IN PROGRESS. R07 must remain on hold.** Offline green tests are not live gameplay acceptance.

## Implemented locally on main

- Read-only existing policy-8 display path: dashboard_feed.py accepts only a tightly bounded optional same-tick capability payload; autoengineer_dashboard.py shows actual read-only planning readiness instead of inventing recipes. The running restricted backend **does not currently emit** this metadata, so it stays unavailable.
- R05 observation mapping in read_only_planning.py covers bounded actually observed position, tick, surface and main inventory, with truncation state; does not infer permission, test success or verified actions.
- R04 optional capability envelope validates 2.x version label, force, research list, enabled first-party content, complete recipe metadata, exact tick/surface and size. Fingerprint includes recipe/mod/research data. Unknown probabilities, quality, temperatures or other recipe fields are rejected, not simplified silently. Actual source authentication will depend on a future authorized backend read-only adapter.
- Read-only recipe preview requires a **qualified Factorio 2.0.77 base-only** source and externally observed machine crafting speed, actual machine power, continuous input rates in items/second (not inventory on hand), and power budget. Complex recipes are unsupported until their math is proven.
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
- https://lua-api.factorio.com/latest/concepts/Ingredient.html — types and fluid/quality complexity.
- Latest upstream API may not equal installed 2.0.77; bind to exact installed game version before any runtime use.

## Remaining mandatory work before R07 acceptance

1. Build and test **a real bounded read-only recipe/research/expansion-version adapter** in the pinned backend source AND the reproducible combined backend-safety.patch. The existing 12-tool policy-v8 backend display does not include catalog metadata. Do not enable arbitrary Lua/RCON or expand gameplay permissions. Test build, compatibility, payload caps, paging, latency, disabled/hidden/unavailable recipes, exact force and surface, fog/private state and patch reconstruction.
2. Full recipe catalog may exceed 128 entries. Add paginated, version-validated read-only access and a stable research/recipe/content fingerprint. Until then, truncated catalog must never certify planner readiness.
3. R06 needs **general multi-product deterministic flow balance**, alternatives, machines and throughput, verified returned catalysts/recycling, quality and stochastic yields, fluid and temperature handling, module/beacon effects, resource and power constraints. Current rate calculations remain bounded, mostly single-machine estimates.
4. Qualify **Space Age, Quality and Elevated Rails individually** in isolated first-party game profiles; handle future 2.x versions separately. Third-party mod adaptation remains R20 last.
5. Perform explicit user-approved **isolated live read-only game verification**, then supervised Semi operations and a measured 1/5/10-minute 300-gears/min physical factory run with negative cases (missing ore, insufficient power, bots/inserters, locked research, save restart, takeover and Stop). Do not alter saves or operate Factorio without authorization.
6. Revalidate legacy CLI denial in the packaged Windows launcher and installed policy-v8 backend before claiming all R01 legacy paths closed.

## Current acceptance status

| Item | Offline evidence | Live acceptance |
|---|---|---|
| R01 legacy direct CLI | Disabled and unit-tested | Retest packaged backend |
| R04/R05 display observation integration | Tests pass | PARTIAL: no live capability catalog |
| R04 full version/research/recipe browser | Bounded parser only | BLOCKED: backend adapter absent |
| R06 item-only simple preview | Test-backed and no gameplay writes | PARTIAL: verified input rates absent |
| R06 300 gears/min physical factory | Source-backed fixture arithmetic | BLOCKED: no physical run |
| Base game future 2.x/Space Age/Quality/Elevated Rails | Explicit fail-closed tests | NOT YET QUALIFIED |
| R07 | Not started | WAIT |

All current work remains uncommitted on local main. No gameplay, save edits, GitHub publication, or model changes authorized by this document.
