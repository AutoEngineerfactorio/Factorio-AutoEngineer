# R05 production/power telemetry — isolated Factorio 2.1.22 live acceptance (2026-10-20)

**Result: PASS for the declared Factorio 2.1.22 production/power telemetry acceptance suite.** This report is **not an assertion that roadmap-wide R05 mechanics evidence, both version targets, Pyanodons stress qualification, or Phase 1A R04–R06 are complete.** The roadmap still marks broad R05 mechanics evidence open.

The tests used the real Factorio 2.1.22 (Space Age and installed input-helper), a restricted 12-tool MCP backend, a connected GUI client, a localhost-only headless server, and separate disposable saves. The RCON script never enabled gameplay MCP writing privileges or inference. Every RCON write was strictly limited to a disposable test copy. The temporary RCON password was generated in memory and discarded. No normal saves/profiles were modified.

## Passed 2.1.22 live telemetry cases

| Scenario | Observed result | Supporting evidence |
|---|---|---|
| Baseline live read | `production=ok`, `power=ok`, 3 item histories, 1 electric network, no stale production reason | `.local/live-pillow/evidence/r05-remaining/baseline.json` |
| Positive native fluid statistics | In-game `on_flow` introduced measurable water + steam and MCP returned 2 fluid histories; proves game-to-backend-to-UI path, **not** physical machine production | `r05-remaining/fluid-positive.json` |
| Live 1-minute milestone | Production and power remained available | `r05-remaining/one-minute.json` |
| Live 5-minute milestone | Production and power remained available | `r05-remaining/five-minute.json` |
| Live 10-minute milestone | Production and power remained available; 2 fluid histories | `r05-remaining/ten-minute.json` |
| Saturation/partial reporting | 25 item names + 15 fluid names injected through native statistics; `production=partial` with explicit reason and **16 item/8 fluid** series bounds | `r05-remaining/partial-cap.json` |
| Electrical shortage | Controlled game interface/load caused consumption satisfaction ~0.009589%, correctly reported in read-only network readings | `r05-remaining/power-shortage.json` |
| Player disconnect | After `#game.connected_players = 0`, outer view `status=unavailable` with no telemetry | `r05-remaining/unavailable-no-player.json` |
| **Actual physical fluid production** | Real in-game **chemical plant** consumed heavy oil and produced **40 lubricant in output fluid box**; native lubricant production rate was nonzero (`4` reported by direct RCON read); MCP returned **heavy-oil and lubricant** histories, `production=ok` | `.local/live-pillow/evidence/r05-final/physical-chemical-fluid.json` and disposable server log |
| **No visible electrical network, player connected** | Removed 7 poles in disposable save; outer view `status=ok`, `production=ok`, and **`telemetry.power.status=unavailable`** with reason `No readable visible own electric network in the local chart window` | `r05-final/no-power-group.json` |
| **Actual dashboard with available network** | Tk GUI rendered correct kW and energy/min readings; production /s and /min switch passed | `r05-final/ui-power-available.png` |
| **Actual dashboard with unavailable network** | Tk GUI displayed reason instead of false zero values; production /s and /min switch still passed | `r05-final/ui-power-unavailable.png` |

The corresponding live-test scripts remain in the ignored private test directory:
`.local/live-pillow/evidence/r05_remaining_live.py`, `r05-final-physical-power.py`, and `r05-final/chemical_fluid_fixture.lua`.
They are development acceptance harnesses, **not production launchers**.

### Interpretation and previous failed fixtures

Two earlier offshore-pump fixtures created an offshore pump and pipes but produced zero native water output, even after a pipe was attached at the fluid connection. These failed **fixture setup** tests did not demonstrate a failing observer. The separately constructed powered chemical plant subsequently produced real lubricant, verified independently in the game's own native statistics and fluid output box, and was visible to the restricted observer. This physical-machine scenario closes the positive-fluid acceptance gap for the declared telemetry suite.

Teleporting the player into a remote unexplored area returned outer `unavailable` and did not prove the power-group unavailable state. The corrected test removed chart-window poles **without disconnecting the player**, directly proving the correct nested power status and reason.

### Measurement and duration qualifications

The 1-, 5-, and 10-minute **wall-clock checkpoints** measured sustained telemetry availability; they are not distinct stored 1-/5-/10-minute production aggregates. The backend emits **60 two-second history samples** at Factorio ten-minute flow precision, giving a 120-second selected history window. It does not claim to retain measured per-output 10-minute long-run aggregates. That broader per-output measured-versus-predicted acceptance belongs with R06/R04–R06 and the realistic factory benchmark.

Production history selects at most 16 item and 8 fluid series; even when `production=ok`, this does not imply every prototype has a nonzero history. Active-history overflow properly sets `partial`. Power is read-only, uses `joules_per_tick` and is displayed as watts/kW and derived energy over time.

### Independent engineering checks

- Full offline Python suite: **431 passed, 134 subtests passed**.
- Ruff: **all checks passed**.
- Isolated restricted backend Release build: **0 compiler errors, 0 warnings**.
- Python production telemetry validation and actual Tk dashboard checks: **both available and unavailable power states passed**.
- Original disposable save SHA256 matched pre-test backup.
- All Factorio server/client test processes were stopped. Zoo Code was not interrupted.
- All existing uncommitted work remains preserved; no commit/push was performed.

### Broader roadmap gates remaining (not hidden or relabeled)

- **R05 Mechanics evidence ledger**: broad per-mechanic observed/permitted/verified/regression coverage across the full intended game and dashboard scope is still open in `ROADMAP.md` and `docs/FACTORIO_COVERAGE_GAP_REGISTER.md`.
- **2.0.77 backport**: separate installed-runtime acceptance for this specific corrected production/power telemetry adapter has not been run in this suite.
- **pY benchmark**: stress and telemetry performance in a separately version-pinned Pyanodons profile remain unverified. The normal Space Age pass does not qualify pY.
- **Phase 1A R04–R06 + H1**: full recipe/research support, arbitrary item/fluid production graph, per-output physical 1-/5-/10-minute rate comparison, recovery/stale-data cases and comprehensive dashboard acceptance remain governed by their own checklists.

**Disposition:** The previously open *Factorio 2.1.22 R05 production/power telemetry cases* are now all demonstrated with real live evidence. Do not mark the entire roadmap R05/Phase 1A complete until the broader version, modded, mechanics and planner acceptance requirements are separately evidenced.
