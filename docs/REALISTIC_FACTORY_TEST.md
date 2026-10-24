# Realistic factory test laboratory — R04–R06 (BEFORE R07)

Status: OFFLINE COUNTER REPLAY AND RESOURCE-CONSTRAINED CHAIN REHEARSAL IMPLEMENTED; native live collection and physical-factory acceptance NOT RUN.

## Objective

Validate AutoEngineer on **every supported producible output**, including items, intermediates, science, fluids, quality variants, and separately qualified first-party/mod profiles. **300 gears per minute is one starter fixture**, not a global production ceiling or a complete test.

Use three distinct evidence levels. The first two are offline-only, not actual Factorio gameplay:

1. **Offline rehearsal (implemented):** agent/factory_reality_test.py checks a game-like 10-minute series of cumulative produced/consumed statistics, item/fluid identities, optional item quality, configurable output targets and independently supplied predicted rates. It computes exact rolling in-game 1/5/10-minute windows from ticks, detects shortages, power-satisfaction dips, missing observations, counters resetting, invalid schemas, wrong units, duplicate products and unsupported evidence. It has no game connection, no blueprint construction, no model call, no recipe physics engine, and no cheats. The included example is intentionally synthetic, with a two-minute underproduction episode; it is not a physically simulated machine network.
2. **Constrained offline chain (implemented):** agent/factory_chain_simulation.py models one fixed 2.1.23 ordinary-recipe flow with 21 electric iron furnaces, 8 electric copper furnaces, 4 gear assemblers, 2 circuit assemblers, 3 cable assemblers, 13 iron ore/s and 4.5 copper ore/s external supply, shared plate/cable material flow and finite transport/power factors. It produces game-tick-aligned synthetic counters for six outputs with a 5:00–7:00 shortage. It is a steady-state math model: no actual belts, inserter cycles, mining, machine buffers, electric-network dynamics or live game.
3. **Approved live test (NOT IMPLEMENTED/RUN):** collect read-only production counters from a distinct, disposable game save in the exact pinned Factorio build. Capture force+surface+version/content/research/prototype fingerprint with timestamps and selected output keys, compare predicted versus observed output, then verify physical factory state and safety against user-approved fault scenarios. Never connect to main saves or an unspecified running process.

## Safe offline example

From `D:\AI\Factorio-AutoEngineer-Source` in PowerShell, with an approved offline-only command:

    python -B -m unittest discover -s tests -p test_factory_reality_test.py -v
    python -B agent\factory_reality_test.py --demo --out .local\test-evidence\realistic-factory-demo-report.json
    python -B agent\factory_reality_test.py --constrained-demo --out .local\test-evidence\constrained-factory-demo-report.json

Create `.local\test-evidence` first if needed. The original `memory\test_runner.py` and `.venv\Scripts\python.exe` commands belong to a different checkout and are not available here. Do not claim all-offline verification from these examples.
The demo has **four independent illustrative output lines**: iron gears, iron plates, electronic circuits and water. Item production falls to 40% for simulated minutes 5–7 and then recovers. For gears, expected final 1-minute measured rate is 300/min, last 5-minute rate is 228/min and last 10-minute rate is 264/min. All measurements are generated offline. Steam/server is NOT launched.

The separate **constrained demo** adds physically consistent intermediate material accounting and machine/ore capacity checks for iron gears and electronic circuits. It has iron plates (780/min nominal), gears (300/min), circuits (180/min), copper plates (270/min), copper cables (540/min), and water (1200/min simulated). During the 5:00–7:00 input shortage, nominal shared item chains fall to 40% while the independent water line remains unchanged; recovered last-minute gear throughput is 300/min, five-minute average 228/min, and ten-minute average 264/min. These are generated synthetic counters, not measured factory output.

Do NOT treat either demo as an in-game factory run, a physics-accurate digital twin, or proof of universal R06 recipe graph correctness.

## Strict counter-capture input schema

Input JSON file (size at most 5 MB), shape:

    {
      "schema": 1,
      "evidence": "external_capture_unverified",
      "profile": {
        "game_version": "2.1.23", "force": "player", "surface": "nauvis",
        "content": ["base"], "tick_rate": 60
      },
      "targets": [
        {"kind": "item", "name": "iron-gear-wheel", "quality": "normal",
         "target_per_minute": 300, "predicted_per_minute": 300},
        {"kind": "fluid", "name": "water",
         "target_per_minute": 1200, "predicted_per_minute": 1200}
      ],
      "samples": [
        {"tick": 0,
         "produced": [
           {"kind": "item", "name": "iron-gear-wheel", "quality": "normal", "total": 0},
           {"kind": "fluid", "name": "water", "total": 0}],
         "consumed": [], "power_satisfaction": 1.0},
        {"tick": 3600,
         "produced": [
           {"kind": "item", "name": "iron-gear-wheel", "quality": "normal", "total": 300},
           {"kind": "fluid", "name": "water", "total": 1200}],
         "consumed": [], "power_satisfaction": 1.0}
      ]
    }

Every tracked production counter must be present in every sample, and counters must be nondecreasing. The optional value of power_satisfaction is nullable: use JSON null when no independently authorized power observation exists; do not manufacture 100% power availability. Consumption rows may be empty when not captured, and unknown consumption must not be misreported as zero. Sample tick is the game's advancing tick count, not wall time. To receive all 1/5/10-minute rates, capture at 10:00 (tick 36000 from baseline) and at its matching 9:00/5:00/0:00 endpoints (ticks 32400, 18000, 0). If a window endpoint is absent it is **NOT_MEASURED**, never guessed or filled with an inventory number. Additional sampling (e.g. once per game second) permits fault diagnosis.

Item quality is keyed separately; fluids have no quality. Per-output targets are customizable. Consumed counters are optional but, when available at both endpoints, reported separately rather than deducted silently. Count origin and provenance are not authenticated by a JSON file: all external captures remain labelled **unverified** until an independently audited live collection session.

Replay existing recorded counters only when the recording is explicitly approved and sanitized:

    .\.venv\Scripts\python.exe -B agent\factory_reality_test.py --input .local\test-evidence\approved-capture.json

No API keys, RCON passwords, game saves, personal paths or executable Lua should be stored in these traces.

## Critical official statistics detail

For Factorio's item and fluid production GUI, production is displayed as the **input** side of LuaFlowStatistics, and consumption as the **output** side (confusing terminology). Thus the eventual adapter must map recorded production from item/fluid statistics input counts, not output counts. Check the exact supported game version before using any runtime API:
- https://lua-api.factorio.com/latest/classes/LuaFlowStatistics.html
- https://lua-api.factorio.com/latest/classes/LuaForce.html

Factorio 2.1.23 confirms LuaForce.get_item_production_statistics(surface) and get_fluid_production_statistics(surface); documented LuaFlowStatistics.get_input_count(id) and get_output_count(id) are the applicable production/consumption totals. Certain quality-specific statistics APIs are newer: do not assume they exist in the installed 2.1.23 build without checking its own runtime API. Verify each variant and quality read against the exact game build before enabling the live collector. The official data examples also identify input_counts as produced and output_counts as consumed. Output count here is **consumption**, not the manufactured output count. This avoids an otherwise serious measurement reversal.

Flow statistics are usually force+surface aggregated, not a machine-level bill of materials. Use a dedicated isolated factory/test force and surface where supported; otherwise other machines and manual crafting may contaminate measurements. Use real prototype/research information to identify what is legal to build. Factorio's statistics may exclude amounts with ignored_by_stats: statistics measure the GUI's counted production, not an infallible full material-conservation proof.

## Proposed live acceptance process — requires explicit user authorization

A. Identify and back up an expendable test save, pinned game build and enabled modules. Do not touch main save or live game. Verify isolated filesystem/config, loopback RCON, one connected player, backend policy-v8, Stop/Take Over and read-only Helper mode.

B. Establish a physically placed small factory legitimately under supervision, with real resource inputs, machines, inserters, belts/pipes, power and researched recipes. In R06 begin with 5 distinct output classes (raw/intermediate, multi-stage, fluid, multi-output/catalyst, stochastic/quality where enabled). User approves each necessary gameplay action independently.

C. Take a 0-minute read-only counter baseline and sample every game second for at least 10 **in-game** minutes at 60 ticks/s, or use the exact in-game tick windows with verified game speed. Record real UPS/wall-time separately; 600 in-game seconds may take longer in real time under load.

D. Record target, deterministic planner prediction and actual production/consumption counters per output. Read power satisfaction, belts/inserters, fluid network and recipe availability from authorized observation adapters when implemented. Never invent absent data. Compare 1/5/10-minute windows, with tolerances and explanations.

E. Approved disruptions one at a time: cut ore supply, insufficient power, backlogged output, missing inserter, research locked, wrong surface, save restart, disconnect, game tick jump, user takeover and Stop. Capture whether the AI detects the real cause and proposes a safe solution. Restoring game state also requires approval.

F. Preserve per-output records across available vanilla/Space Age/Quality/Elevated Rails profiles; the architecture must accept all dynamic products, including third-party adapters once R20 is reached. A handful of samples is coverage of **classes**, not 100% all-catalog physical evidence.

G. Before R07, independently review R04 capability catalog, R05 coverage ledger, R06 flow solver completeness, backend build/runtime, live measurement evidence, uncertainties, stability/UPS and controls. Do not infer R07 approval merely because this replay passes.

## Result status and expected next engineering work

- Offline flow-statistics replay: AVAILABLE, 20 regression tests.
- Constrained recipe/ore/machine/transport/power chain: AVAILABLE, 8 focused regression tests (28 targeted tests total).
- Real native stats exporter: NOT IMPLEMENTED; needs version-aware, allowlisted, read-only adapter and human approval.
- Physical machine simulation: NOT IMPLEMENTED; demo rates are illustrative and never proof of physics fidelity.
- Physical factory tests and 1/5/10 minute measured runs: NOT RUN.
- All-item/expansion/mod coverage: DESIGNED FOR dynamic identities, NOT physically verified.
- R07: ON HOLD by docs/R04_R06_PRE_R07_ACCEPTANCE.md.

Use this laboratory to build the real-game connector as a separately reviewed change, not to substitute a synthetic fixture for real game acceptance.
