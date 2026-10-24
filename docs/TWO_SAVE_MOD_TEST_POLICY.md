# Two-save Factorio mod test policy

**Factorio 2.1.23 is the sole supported development and testing version.** One
persistent disposable test save is used for it. The archived 2.0.77 and 2.1.22
installations, profiles and saves are preserved as historical records and are
never used as active test targets. Future game-version upgrades require a
deliberate compatibility review rather than automatic assumptions.

| Factorio version | Allowed test-save path | Test executable |
|---|---|---|
| **2.1.23 ACTIVE** | .local/launcher-profiles/2.1.23/data/saves/autoengineer-test.zip | D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe (verified actual version 2.1.23; inherited directory name) |

These paths are proposed under Git-ignored `.local`. **Do not automatically generate new saves** if the expected one is absent; first inspect existing isolated profiles and obtain a verified game-launch setup. Do not use main-game saves.

- No separate persistent save for each test/mod. Reuse the designated disposable save.
- A test needing a clean state may restore the designated baseline, but must not create a second persistent save or overwrite the archived 2.0.77/2.1.22 saves.
- A mod must be verified compatible with Factorio 2.1.23 before it is installed into the 2.1.23 test profile. Do not assume a mod supports 2.1.23; check its own metadata and changelog.
- For each run: run offline preflight, validate Lua structure, launch correct game/mod directory with disposable save, inspect exit code and logs, then compare expected vs actual behavior.
- Do not claim mod-load acceptance until observed in the correct game runtime.
- Keep pY test mods separate from vanilla test profiles; continuous synthetic pY graph benchmarking does not require additional gameplay saves. If a future pY live test needs a distinct save, ask before changing the disposable-save rule.
- Never disable permissions or expose arbitrary Lua/RCON during testing.

## Launcher profiles
- **2.1.23 active:** .local/launcher-profiles/2.1.23/launcher.local.json
- Archived, retained for rollback and historical evidence only, never for routine testing: `.local/launcher-profiles/2.0.77/launcher.local.json` and `.local/launcher-profiles/2.1.22/launcher.local.json`
- The active 2.1.23 profile passed `agent.launcher_services.Profile` validation on Windows. This does not imply an actual graphical host/RCON startup test.


**Current version decision (2026-10-20):** Factorio 2.1.23 is the only active development/test target. Use the versioned input-helper 2.1.23 and an isolated 2.1.23 launcher profile. Older versions remain preserved; historical acceptance is not transferable.
