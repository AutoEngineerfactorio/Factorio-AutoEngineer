# Two-save Factorio mod test policy

**Exactly two persistent disposable test saves, one per Factorio executable version.**

| Factorio version | Allowed test-save path | Test executable |
|---|---|---|
| 2.0.77 | `.local/launcher-profiles/2.0.77/data/saves/autoengineer-test.zip` | `D:\AI\Factorio-Isolated-2.0.77\Factorio_2.0.77\bin\x64\factorio.exe` |
| 2.1.22 | `.local/launcher-profiles/2.1.22/data/saves/autoengineer-test.zip` | `D:\AI\Factorio-Isolated-2.1.22\Factorio_2.1.22\bin\x64\factorio.exe` |

These paths are proposed under Git-ignored `.local`. **Do not automatically generate new saves** if the expected one is absent; first inspect existing isolated profiles and obtain a verified game-launch setup. Do not use main-game saves.

- No separate persistent save for each test/mod. Reuse each version's designated disposable save.
- A test needing a clean state may restore the version's designated baseline, but must not create a third persistent save or overwrite the other version.
- Factorio 2.1-only mods must not be installed into the 2.0.77 test profile. Test 2.0 compatibility only with a separately version-compatible mod build and confirmed API behavior.
- For each run: run offline preflight, validate Lua structure, launch correct game/mod directory with disposable save, inspect exit code and logs, then compare expected vs actual behavior.
- Do not claim mod-load acceptance until observed in the correct game runtime.
- Keep pY test mods separate from vanilla test profiles; continuous synthetic pY graph benchmarking does not require additional gameplay saves. If a future pY live test needs a distinct save, ask before changing the two-save rule.
- Never disable permissions or expose arbitrary Lua/RCON during testing.

## Launcher profiles
- 2.0.77: `.local/launcher-profiles/2.0.77/launcher.local.json`
- 2.1.22: `.local/launcher-profiles/2.1.22/launcher.local.json`
- Both passed `agent.launcher_services.Profile` validation on Windows. This does not imply an actual graphical host/RCON startup test.

