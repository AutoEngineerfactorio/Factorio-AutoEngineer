# R05 mechanics evidence ledger — primary versioned truth table

**Current version note:** This dated 2.1.22 / 2.0.77 matrix remains historical. Current target 2.1.23 has independently passed an updated Lua helper mod-load smoke, but does not automatically inherit all previous R05 telemetry/coverage acceptance.

Updated 2026-10-20. **Project status: COMPLETE FOR NOW (administratively/provisionally parked at the user's request; remaining acceptance evidence deferred).** This is **not** a declaration that all R05 mechanics, Pyanodons, or 2.1.23 live scenarios passed. Reopen when a specific dependency, observed defect, or later H1 acceptance requires a missing case. **Evidence status remains OPEN/PARTIAL wherever the table says so.** This is the required R05 evidence ledger for witnessed game states, read-only observations, planned mechanics, permission boundaries, and regression tests. It is NOT a blanket sign-off for all of Factorio. Keep it aligned with `ROADMAP.md`, `FACTORIO_MECHANICS_REFERENCE.md`, `FACTORIO_COVERAGE_GAP_REGISTER.md`, `R05_LIVE_ACCEPTANCE_2026-10-20.md`, and the R04–R06 acceptance gate.

**Classification:** `PASS-live` = directly observed, version-pinned game scenario with preserved evidence; `PASS-offline` = deterministically tested without installed gameplay; `PARTIAL` = observed only for the specified subset; `OPEN` = no qualifying proof; `N/A-to-R05` = mechanics execution belongs to another named R milestone, not claimed as R05 gameplay support. A feature's presence in code/docs alone is NOT a pass. Do not confuse model-discovered links with executed tests.

## R05 observed mechanics / version-specific verification

| Case | Observation/feature and rights | 2.1.22 (Space Age, Quality, Elevated Rails) | 2.0.77 (same first-party flags) | Remaining proof |
|---|---|---|---|---|
| R05-T01 | Actual force-scoped item flow, read-only Helper | **PASS-live**, 3 item series and `production=ok` | OPEN | Active item generation/stall/freshness variability by profile |
| R05-T02 | Actual fluid flow, read-only Helper | **PASS-live**, heavy oil input, real chemical plant crafting lubricant, nonzero native flow and 2 backend fluid series | **PASS-live**, separate disposable 2.0.77 chemical-plant craft, 20 lubricant output, 2 native-backed fluid series | Dynamic fluid temperature/backpressure/long-window aggregates tracked under R06/R13 |
| R05-T03 | 16 item/8 fluid history selection and partial status, no false complete catalog | **PASS-live**, 25/15 names generated via native stats, bounded series + `partial` reason | OPEN | pY active-volume stress |
| R05-T04 | Power production/load/SI rates/derived energy, read-only Helper | **PASS-live**, electrical network measurement and Tk kW, kJ/s, MJ/min | **PASS-live for historical-only power**: version-gated native `LuaFlowStatistics` returned 156.30 J/tick input/output, Tk displayed 9.38 kW historical averages; capacity/satisfaction intentionally unknown | Focus remaining multi-grid/storage/UPS evidence on 2.1.22 |
| R05-T05 | Brownout / consumption satisfaction (R05 observation, R13 recovery separate) | **PASS-live**, 0.009589% electric satisfaction under controlled disposable load | OPEN | Multiple-grid policy and time-varying shortage |
| R05-T06 | Power unavailable while player connected, no silent zero | **PASS-live**, seven test poles removed, `telemetry.power=unavailable` with explanation | OPEN | Other visibility/multiplayer force cases |
| R05-T07 | No connected player / controller unavailable, no invented data | **PASS-live**, outer `status=unavailable` with no telemetry | OPEN | Vehicle, death/respawn, spectator, remote-view |
| R05-T08 | Timestamp, tick and stale/reconnected planning gating | PASS-offline, strict freshness checks | OPEN | Live pause, reconnect, tick regressions and force/surface switch |
| R05-T09 | 1 / 5 / 10 minutes of backend runtime observation | **PASS-live** for sustained availability at each wall-clock checkpoint | OPEN | **Not** validated 1/5/10-minute per-output aggregates; 60 samples × 2 sec = 120-sec display |
| R05-T10 | Real installed dashboard graphs and rate-switching | **PASS-live replay + real Tk UI**, /s ↔ /min, available and unavailable power | OPEN | Continuous GUI refresh/stall/recovery, visual stress |
| R05-T11 | Version/expansion and runtime capability truth (R04-linked) | PARTIAL, 2.1.22 installed and first-party modules loaded; telemetry usable | OPEN | Live paginated recipe/research profile verification |
| R05-T12 | Charted fog, map chunk/force-specific visibility and surface changes (G-B02) | PARTIAL, local chart map tests in earlier isolated foundation; not full scenario coverage | OPEN | Force/fog/remote-view/surface transitions and stale-cache invalidation |
| R05-T13 | Multiplayer force/permissions, owner vs observer (G-B03) | OPEN | OPEN | Two-player independent connection, force change, read permissions and lag |
| R05-T14 | Character crafting/cancel/inventory/reach/cursor (G-B04) | PARTIAL, earlier bounded mining/crafting controls; no complete coverage | OPEN | Refunds, swapping, ghost/cursor and inventory-filter cases |
| R05-T15 | Death, respawn, corpse, inventory ownership (G-B05) | OPEN | OPEN | Disposable death+respawn, no stale player state |
| R05-T16 | Vehicle/Spidertron player/remote controller observations | PARTIAL, source remote-view tests previously recorded; not full vehicles | OPEN | Controller transitions, vehicle entity, no fabricated inventory |
| R05-T17 | Research/force/surface/quality cache invalidation (G-A05) | PASS-offline for same-snapshot R04 page assembler; not R05 live | OPEN | Live toggled research/force/surface/quality and consistency |
| R05-T18 | Evidence is positive, negative or uncertain (G-A06) | **PASS-ledger** for explicitly listed cases and failures | PARTIAL | Mechanic-wide entries must not infer pass from evidence presence |
| R05-T19 | Space Age first-party changed API, empty surfaces/prototypes (G-S19) | PARTIAL, 2.1.22 Space Age Nauvis read; no other planets | PARTIAL, first-party modules load at 2.0.77 | Empty surfaces, prototype changes, offworld observation |
| R05-T20 | pY telemetry/catalog performance (separate isolated suite) | **PASS-offline only for pY-shaped synthetic graph**, 100/1k/10k nodes, NOT real pY mods | N/A | Pinned actual pY modpack profile, sanitized catalog, data loading, telemetry/UPS/latency/memory |
| R05-T21 | Version isolation and save integrity | **PASS-live** disposable-only copies and SHA256 original check | PARTIAL: startup safe, original 2.0.77 save unchanged | Full authenticated/character-present 2.0.77 telemetry |
| R05-T22 | Permission boundary: Helper may observe, not act | **PASS-live** restricted 12-tool surface; game fixture writes were test-admin RCON on disposable saves only | PARTIAL, 12 tools advertised in RCON backport probe | Live verification of read-only path under varied modes, auth/reconnect |
| R05-T23 | Observed vs estimated vs unavailable provenance for dashboard | PARTIAL, production/power statuses and Tk warnings proven | OPEN | Mark all other optional layers and source/version/staleness consistently |
| R05-T24 | Large-base performance/UPS and UI latency | OPEN | OPEN | Repeated sampled timing/memory/UPS budgets and big-game profile |
| R05-T25 | Quality-enabled versus disabled flags | PARTIAL, Quality-enabled tested as loaded | PARTIAL, module flag verified installed | Quality-disabled isolated profile and expected missing prototype states |
| R05-T26 | Underlying R13 recovery / R14 combat / R11 trains / R12 robots / R15 planets | **N/A-to-R05** as *action/autonomy proof*; R05 must still record observed/unavailable state | N/A-to-R05 | Do not relabel separate implementation milestones as completed |
| R05-T27 | 2.0.77 versioned live backport of corrected R05 source | N/A | **PASS for scoped compatibility:** live production `ok`, physical lubricant, historical network 1 power `partial` with truthful provenance, no stale reason, read-only MCP, isolated save; lacks 2.1-only capacity/satisfaction by design | Compatibility retained; per user request defer all further 2.0.77 work and focus new development on 2.1.22 |

## Detailed reproducible evidence

- `docs/R05_LIVE_ACCEPTANCE_2026-10-20.md`: declared 2.1.22 production/power live suite, outcome, versions, RCON fixture limits, exact path names.
- `.local/live-pillow/evidence/r05-remaining/`: baseline, native fluid, 1m/5m/10m, selected-history overflow, shortage and disconnected outer-unavailable saved JSON.
- `.local/live-pillow/evidence/r05-final/`: real chemical plant producing lubricant (physical, not statistics injection), connected-player power unavailable, actual Tk UI screenshots.
- `python -m pytest -q tests` and `python -m ruff check agent tests`: **434 Python tests, 134 subtests**, Ruff clean on 2026-10-20 after 2.0 compatibility regression additions; not a replacement for game checks.
- `python -m benchmarks.modded_recipe_graph --sizes 100 1000 10000`: synthetic 100/1k/10k intermediate recipe graphs; **actual_pyanodons_data=false** for every row, 10000 case ~12002 nodes, 51 cycles, ~115.482 ms traversal, ~14.768 MiB peak Python allocations. Not a pY gameplay certification. Independent `python -m unittest tests.test_modded_recipe_graph_benchmark`: 3 tests passed.
- `.local/live-pillow/evidence/r05-backport-2077/`: live 2.0.77 scoped compatibility now verified for native historical power plus physical fluids. `live-telemetry-physical.json` stores the network 1 `partial`/historical evidence; `ui-2077-historical-power.png` displays the real Tk view. See `R05_2077_BACKPORT_EVIDENCE_2026-10-20.md`. Never copy or publish credentials, player data, saves or full private logs.

## Mandatory closeout checks

- No `OPEN` or `PARTIAL` row that is genuinely within the intended R05 *evidence* scope may be silently treated as done. Any deferred feature must have the explicitly named separate owner, expected observable fields and safe regression entry.
- Recorded `observed/planned/permitted/verified/regression` state must be auditable for each included mechanic **per version/profile**. Correctly report known absent permissions.
- R05 is **not** R06 production math, R07 blueprints, R08 placements, R11 trains, R12 robots, R13 automatic recovery, R14 combat or R15 Space Age gameplay execution. Observability cross-references are still R05 work.
- Both pinned runtime targets need same correction verified independently; pY remains continuously benchmarked as synthetic until real isolated version-pinned content is authorized and installed, then record real observations separately.
- Maintain exact evidence paths, repeatable offline tests, and fresh isolated game runs for every claim. Never mark R05 complete solely to satisfy a deadline or user preference.
