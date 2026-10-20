# Factorio 2.1.23 portable and Lua API migration — 2026-10-20

**Current active development and integration version:** Factorio 2.1.23. The 2.1.22 installation and its installed-runtime evidence are retained as rollback/historical records; 2.0.77 is archived.

## Verified portable executable

- The portable executable reports ProductVersion 2.1.23:
  D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe
- The game was updated officially from a copied 2.1.22 install; the containing directory name is historical, not the executable version. Do not rename a game directory while running.
- The user-owned game and account were not modified during this migration.
- The independently copied rollback executable still exists under D:\AI\Factorio-Isolated-2.1.22.

## Active AutoEngineer paths

- Isolated launcher: .local/launcher-profiles/2.1.23/launcher.local.json
- Private server/client config and disposable save: .local/launcher-profiles/2.1.23/
- Enabled mod folder: .local/mod-test-mods/2.1.23/autoengineer-input_2.1.23/
- Versioned, editable mod source: factorio-mod/autoengineer-input_2.1.23/
- New isolated telemetry server profile and smoke: .local/live-pillow-2.1.23/
- Historical 2.1.22 Lua mod, launcher/test profiles and evidence remain preserved.

The 2.1.23 input-helper package has mod version 2.1.23 and Factorio major-version compatibility 2.1. It requires base >= 2.1.23. Its existing movement/mining/building/cursor control bindings remain intact; the 2.1.23 package additionally treats on_player_respawned as a human-takeover event, invalidating a stale controller lease. It uses player_index only.

## Exact installed Lua API delta

Compared the cached official-style runtime-api.json for 2.1.22 against the runtime-api.json shipped with this installed 2.1.23 game. Both report API version 6. All named runtime classes, events and defines were retained; no methods or attributes were removed from LuaPlayer, LuaBootstrap, LuaEntity, LuaFlowStatistics or LuaElectricNetwork relevant to the input guard / R05 observer.

The discovered changes are:
1. LuaGameScript.take_screenshot adds the optional hide_health_bars parameter.
2. on_player_respawned removes the optional player_port field. The input guard never used that field and now explicitly handles respawn by player_index.
3. ItemPrototypeFlag adds disable-logistic-overlay.

**Do not assume that a new game patch requires rewriting unchanged Lua APIs.** Existing backend Lua queries stay intact until an exact-version failure proves otherwise.

## Live and offline verification

- Real headless Factorio 2.1.23 launched successfully from the new isolated profile, with base 2.1.23, Space Age 2.1.23 and the new AutoEngineer input-helper mod 2.1.23 loaded.
- The test server bound to localhost-only game/RCON ports, started successfully, reported no startup errors and was stopped afterward.
- The main user Factorio game stayed open during this headless smoke.
- New API tests: tests/test_factorio_2123_api.py.
- Existing Lua runtime tests: tests/test_input_helper.py.
- Mod package format test: tests/test_factorio_mod_preflight.py.
- Game profile staging, smoke scripts and their private logs are in .local/live-pillow-2.1.23/.

**Acceptance boundary:** A successful Lua/mod-load smoke is not yet a complete, connected-player 2.1.23 telemetry/live R05 acceptance. Previous 2.1.22 R05 production/power measurements remain historical, and the full R04–R06 / H1 roadmap gates are still open.

## Next integration actions

Use the new isolated 2.1.23 launcher and the restricted backend for a live connected-player game test of R04, R05 telemetry, and R06 planning. Do not reuse the previous version's saved data as proof. Do not start semi- or full autonomy while gates are pending.
