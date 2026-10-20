# Permanent Factorio mod testing and safety contract

For **every Factorio mod source change**, read `docs/TWO_SAVE_MOD_TEST_POLICY.md`, `docs/OFFLINE_FACTORIO_API.md`, `docs/FACTORIO_SCRIPTING_API_REFERENCE.md` and `.clinerules/04-factorio-lua-references.md`. Use the roadmap for feature scope.

## Version and documentation gate
- Identify the installed test version and enabled mods before using a Factorio API.
- Read the local reference at `.local/factorio-api-offline/<version>/files/`: `runtime-api.json`, `prototype-api.json`, and version-specific HTML.
- Treat `control.lua` (runtime), `data.lua` (prototype registration), and `settings.lua` (settings stage) as distinct lifecycles. Never guess globals, method signatures, or events.
- Prefer local offline references; consult official internet sources when local docs are insufficient, and cite the actual checked version.

## Tooling gate
- Use Lua Language Server (LuaLS), Factorio Modding Tool Kit, and Factorio Lua API autocomplete when installed and available in VS Code. LuaLS and autocomplete report diagnostics; they do not guarantee real game compatibility.
- For Python, use the interpreter selected in `.vscode/settings.json`. Confirm dependencies and Pylance diagnostics; do not suppress `reportMissingImports` as a workaround.
- If an extension command/debugger is unavailable to Zoo, report that limitation; do not pretend an extension ran, and do not use arbitrary RCON/Lua execution to bypass it.

## Only two persistent test saves
- 2.0.77: `.local/launcher-profiles/2.0.77/data/saves/autoengineer-test.zip`
- 2.1.22: `.local/launcher-profiles/2.1.22/data/saves/autoengineer-test.zip`
- Use the corresponding launcher JSON at `.local/launcher-profiles/<version>/launcher.local.json` and isolated executable. Do not create a third persistent test save or use normal Steam/main saves.
- A mod targeting 2.1 must not be loaded as if it were compatible with 2.0. Test only a verified version-compatible build against 2.0.
- pY synthetic stress tests remain isolated; adding a separate persistent pY gameplay save requires explicit approval.

## Required quality gate
1. Inspect scoped files and confirm exact game/API version; make a bounded plan.
2. Make only approved code changes; never widen Zoo auto-approval or command allowlists.
3. Run `python -m unittest discover -s tests -p test_factorio_mod_preflight.py -v` and relevant offline tests.
4. Check LuaLS/Pylance findings and Lua mod-stage correctness. No suppressing diagnostics merely to get green status.
5. When safe and permitted, load the relevant mod and designated save using the correct isolated Factorio executable, inspect stderr/logs and process exit status, and verify actual runtime behavior beyond load where required.
6. Report **passed**, **failed**, and **not run** distinctly, with commands, paths, version, and evidence. Offline preflight is not a live gameplay pass. Stop on blockers; never invent success.
7. Never execute arbitrary Lua/RCON, touch production saves, run unapproved destructive actions, or enable automatic tool approvals.

Existing `.clinerules/01-project.md` and other project rules still take precedence when stricter.
