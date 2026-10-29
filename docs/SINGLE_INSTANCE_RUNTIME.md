# AutoEngineer single-instance runtime — 60 UPS protection

## Decision (2026-10-27)
**Default: one graphical Factorio 2.1.23 process hosting its own local multiplayer game.**
Do not start a second Factorio headless process and then join it merely to
enable RCON. Factorio supports `--host SAVE` (see official command-line wiki)
and a local GUI-host RCON endpoint through the profile's private `config.ini`:
`local-rcon-socket=127.0.0.1:PORT` and `local-rcon-password`.
Never put the GUI-host password on command lines, in Git or in documentation.

This is already an option in `agent/launcher_services.py`:
`game_mode="graphical-host"` (the default) uses `--host` instead of
`--start-server` + `--mp-connect`. It requires a disposable, isolated profile,
validated save, loopback RCON, matching private secret, and nonadvertised server
settings. Do not migrate an existing two-process live test while running.
Dedicated mode remains available explicitly for isolated compatibility tests.

## Runtime topology
One graphical Factorio multiplayer host (game + rendering + RCON)
→ existing restricted C# backend / registered read commands
→ shared observation coordinator (cache + bounded requests)
→ Qt dashboard + AI Helper planner (consumers, not independent pollers).
One separate AI inference worker is optional; use local llama.cpp OR an
approved external provider, not parallel local GPU models by default.
Semi-autonomous and full-autonomous control require their *existing* separate
security/approval gates; **full autonomy is still locked**.

## Safety and performance contracts
- Factorio simulation and rendering are never downprioritized or affinity-pinned
  by AutoEngineer. The interactive dashboard stays at ordinary priority.
- New launcher-owned `llama` processes are started BELOW_NORMAL on Windows;
  attached/user-owned inference processes are never touched. Existing running
  Factorio sessions and models are never reprioritized or stopped.
- `agent/performance_governor.py` supplies a pure `UPSGuard`: sample
  real Factorio ticks against a monotonic clock over at least 4 seconds;
  hysteresis requires multiple healthy/degraded samples. It returns distinct
  budgets for unknown, healthy, degraded and critical rates. Optional
  inference and catalog work should run only when `ai_allowed` or
  `catalog_allowed` is true. Unknown, paused and slow games back off.
- **Live-tested 2026-10-27:** `agent/ups_inference.py` gates new local AI
  HTTP completions in `supervised_agent.py`, `live_planner.py`, and
  `ai_movement.py`. It demands four registered status observations over
  ~12.6 seconds at near-standard UPS; unknown/paused/slow/overspeed refuses
  inference. Requests are serialized per agent process. It is **admission
  control only**: a previously admitted long-running inference is not
  interrupted mid-completion; there is not yet a cross-process global queue.
- **Implemented and offline-tested:** `qt_observation_bridge.py` adjusts its
  existing status+telemetry polling to 2s healthy, 4s unknown, 5s degraded,
  or 10s critical (minimums if configured slower). No extra RCON polling
  thread or recipe-catalog polling was introduced. Do not claim live
  acceptance of this last observer change until separately benchmarked.
- Existing observation TTLs are status 1s, telemetry 2s, map 4s,
  catalog 30s, with <=2 in-flight requests; no full catalog on telemetry
  tick. These are cache policies, not a license to add additional pollers.
- For a Ryzen 7 5800X + RX 6700 XT 12GB, start with **one** local model,
  one AI inference at a time and bounded context (avoid full 12GB VRAM
  allocation). Actual concurrency, GPU layers and CPU threads must be tuned
  against a real live workload. Do not force CPU affinity or promise 60 UPS.
- Never treat GPU FPS as game UPS, or a paused/speed-modified game's tick
  count as an ordinary 60 UPS reference. UPS is measured, not assumed.
- Avoid polling all recipes or regenerating large JSON catalogs during normal
  game ticks; cache by profile/mod/research fingerprint and fetch on demand.

## Technical blockers before declaring the design complete
1. **Resolved and live verified 2026-10-27:** launcher RCON health now
   uses registered `/autoengineer-observe status`, not `/silent-command`.
   Failed/unknown observations are not accepted as safe for saving.
2. **Resolved and live verified 2026-10-27:** Qt parses the new R09 live
   telemetry contract; electric subnetworks now use `LuaElectricSubNetwork.id`
   and parent-network `flow_last_tick`. A disposable graphical-host creative
   run observed 18 flow rows, 3 active flows, one electrical network and
   186 kW generation, with a successful offscreen Qt Electrical render.
3. **Resolved at the initial integration level, 2026-10-27:** live UPS gate
   wired into three game-attached AI inference paths and adaptive polling
   wired into the Qt observer. Long-running inference cancellation and a
   global cross-process inference queue remain future improvements.
4. **Partially verified 2026-10-27:** single graphical-host creative save
   plus local FrogNano-4B Q4 produced a real 48-token completion. UPS while
   sampling inference averaged **60.03**, minimum sampled **59.11**;
   model-loaded baseline **59.66**. Model process RSS peaked at **2.76 GB**.
   Factorio without the LLM measured **60.17** before creative setup and
   **60.04** afterwards. These are short measurements, not a UPS guarantee.
   **Sustained tests PASSED 2026-10-27:** 300 seconds for each of the
   vanilla/Space Age and full Pyanodons mod profiles with 20/20 real
   256-token model completions per profile. Both averaged 60.00 UPS;
   sampled minima were 59.58 and 59.55 respectively, with no samples
   below 59. See `memory/LONG_STRESS_VANILLA_PY_2026-10-27.md`.
   **Still pending:** full operating pY megafactory, graphical FPS,
   GPU VRAM/utilization, concurrent Qt charts/catalog and mid-request
   inference interruption. This is not a guaranteed 60 UPS claim.
5. **Still pending:** graphical-font/render inspection on Windows (offscreen
   Qt captures lack glyphs), restart/reconnect safety, and remaining
   read-only AI Helper workspaces. Do not assume full autonomy is unlocked.
   The creative `/c` commands ran **only** on a copied disposable save.

## Verification and rollback
Offline checks: `python -B -m unittest tests.test_performance_governor
tests.test_launcher`; plus `ruff check`, `git diff --check`, VS Code Problems.
Production Tkinter remains the launcher default until Qt achieves parity.
No active Factorio processes, game saves, host configurations, credentials,
ports or model files were modified as part of this design change.
