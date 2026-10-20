# R05 Factorio 2.0.77 installed-backend acceptance — 2026-10-20

**Final compatibility status: PASS for the scoped 2.0.77 historical-electricity fallback, physical-fluid observation, read-only MCP and isolated-save checks.** This does not mean 2.0.77 supports 2.1.22's instantaneous power metrics. It does not close roadmap-wide R05.

This is a test of the isolated **Factorio 2.0.77** binary and Space Age/Quality/Elevated Rails first-party content. It uses the same restricted patched backend as the Factorio 2.1.22 test, 12 exposed MCP tools, localhost-only server/client, and a disposable copy of `.local/launcher-profiles/2.0.77/data/saves/autoengineer-test.zip`. The game user's credentials and authentication tokens were not read or copied. Test authentication used a temporary RCON secret generated in memory, removed afterward.

## Passing cases

- Isolated 2.0.77 client joined the local server; original 2.0.77 save was SHA256-confirmed unchanged.
- The original disposable save started with a non-character controller, resulting in the expected outer `status=unavailable`. For testing only, the copy was switched to god controller then given a character through documented `p.create_character()`.
- The restricted MCP backend enumerated **12 tools**, including `autoengineer_view`, and returned `status=ok`, `production.status=ok`, without a stale `production.reason`.
- A real chemical plant created in the disposable save consumed heavy oil and crafted **20 units of lubricant**, with the native lubricant flow statistic at **2** in the recorded observation. The restricted backend returned **heavy-oil** and **lubricant** fluid series.
- No ordinary saves were touched, the temporary credential was discarded, and all test-owned server/client processes were stopped after each run. The signed-in primary client was never targeted for termination by the test harness.

## Historical root cause (resolved by the compatibility adapter)

- Before the fix, the 2.0.77 backend returned `power.status=unavailable` with reason **`Electric network statistics read failed`**.
- A separate test grid immediately next to the connected character had a visible own-force medium pole with network id **2**; a generation interface and separate test load both joined network **2**. This proves the network **exists**.
- The original backend Lua adapter accessed `pole.electric_network.parent_network.flow_last_tick`. That `LuaElectricNetwork` object exists in pinned 2.1.22 but **does not exist in pinned Factorio 2.0.77**. The patched adapter now has an explicit version-gated fallback.
- The official 2.0.77 runtime API instead exposes **`LuaEntity.electric_network_statistics`** as `LuaFlowStatistics`. Electricity `get_flow_count` readings are normalized to **joules per tick**, and unlike 2.1.22 instantaneous network samples, do **not** directly provide capacity limits or consumption/production satisfaction.
- Direct RCON validated `pole.electric_network_statistics` exists, but its `input_counts` and `output_counts` remained empty in the tested 2.0.77 artificial source/sink fixture, despite both being network-connected. Do not count them as positive live electrical power flow.
- **Implemented and live-verified:** Version-gated 2.0.77 reads `pole.electric_network_statistics` with native historical electricity flow counts and emits `power.status=partial` plus explicit provenance. The strict validator and dashboard accept that limited schema, never fabricate 2.1-only capacity, satisfaction or accumulator metrics, and preserve the original 2.1.22 instantaneous branch. Tested with a real game MCP capture: electrical network 1 reported **156.30092594 J/tick historical input and 156.30092594 J/tick historical output**, equivalent to **9.38 kW at 60 ticks/second**. Both histories were present; `history_available=true`. The dashboard printed this as an observed one-minute average, with unknown unavailable metrics.

## Evidence and limitations

- `.local/live-pillow/evidence/r05-backport-2077/live-telemetry-baseline.json` — real connected 2.0.77 production observation.
- `.local/live-pillow/evidence/r05-backport-2077/live-telemetry-physical.json` — physical chemical plant and 2 real fluid histories.
- `.local/live-pillow/evidence/r05-backport-2077/live-telemetry-physical.json` — **newly verified** network 1 `power=partial`, source `legacy_statistics`, native input/output; note this filename was overwritten with the post-fix live capture. Earlier failed `live-telemetry-power-grid.json` is evidence of the pre-fix failure.
- `.local/live-pillow/evidence/r05_backport_2077_physical.py` and `r05_backport_2077_power_diagnostic.py` — isolated test harnesses; they are not production game launchers.
- Pinned local 2.0.77 `runtime-api.json` was used to confirm the supported electric statistics API and normalization. No live Pyanodons gameplay, quality-disabled profile, or full R05 mechanics matrix was tested here.

**Project version decision:** Going forward, the user has prioritized **Factorio 2.1.22 only** for new development and acceptance work. Preserve this 2.0.77 compatibility fix but do not continue 2.0.77 testing/maintenance unless separately requested. The broader R05 mechanics ledger and 2.1.22 modded benchmark acceptance remain distinct gates.

**Release gate:** This does NOT mark roadmap-wide R05 complete. No R06, R07, H1 or autonomy gate is unlocked by these tests.
