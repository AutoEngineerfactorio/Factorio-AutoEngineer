# Permanent edge-case, failure and compatibility safeguards

Apply to every AutoEngineer task with rules 01-09. These are **checks and fail-closed behavior**, not claims that a feature is implemented or tested. Keep all existing safety constraints, individual tool approval, and the policy preserving existing test saves without creating additional persistent saves.

## Tooling and repository
- Distinguish PowerShell syntax errors, nonzero process exits, missing PATH tools, disabled VS Code extensions, incorrect VS Code profiles, stale language-server state, and genuinely missing dependencies.
- Account for spaces, Unicode, backslashes, long Windows paths, quoting, CRLF/BOM, permissions, file locks, files absent or changed since discovery, and Git untracked/staged/unstaged differences.
- Never overwrite concurrent Zoo/ChatGPT work. Check `git status --short` and targeted diffs before edits; do not sweep all changes into one commit. Avoid secrets, large archives, saves, models, backups, and `.local` in commits.
- Use bounded searches and avoid repeated `dir` loops. Stop after two substantially identical failed attempts and report evidence.

## Factorio API and mod lifecycle
- Pin installed executable and enabled mod set before using API definitions. Fail closed on missing/renamed runtime fields, removed events, type/nullable changes, version-gated quality/platform/planet functionality and 2.0 vs 2.1 divergence. The supported target is 2.1.23; treat any 2.0/2.1.22 API name as historical and unverified for the current build.
- Settings/prototype/runtime contexts differ: `data:extend` belongs to data stage, while `script.on_event` belongs to runtime. Verify `script`, `game`, `storage`, `remote` and LuaObject lifetime at the correct stage; account for `on_init`, `on_load`, migration and configuration changes.
- Treat custom inputs, event IDs, remote interfaces and mod dependencies as optional/version-dependent until verified. Handle absent players, invalid entities, disconnected clients, missing surfaces/forces and deleted prototypes without crashing.
- Respect determinism and multiplayer sync. Avoid unbounded per-tick scanning, uncontrolled remote calls, unbounded log output, and executing arbitrary Lua or RCON through an AI-generated command.

## Telemetry, AI Helper and complex mods
- Handle unknown or locked recipes, alternate production pathways, crafting categories, catalysts, byproducts, probabilistic yields, circular chains, fluids/temperature, modules, quality, research limitations, spoilage and logistic constraints.
- Handle missing/renamed prototypes, multi-surface/planet logistics, train/circuit signals, platforms and power brownouts. Distinguish zero, missing, stale, partial and delayed telemetry; never fabricate state or success.
- Pyanodons is a continuing **isolated synthetic benchmark** for large recipe/technology graphs and throughput; do not mix it into normal test profiles or add gameplay saves without approval. Different mod sets may alter recipe unlocks and dependencies.

## Tests and recovery
- Preserve exactly the existing persistent test saves: the 2.1.23 save is supported, and the 2.0.77 and 2.1.22 saves are archived rollback material. Use the version-specific launcher profile, isolated mod directory, and correct executable; no Steam/main-save writes and no new persistent save.
- Run static/offline tests and source-versus-staged consistency first; do not mistake a successful 10-tick load benchmark for UI behavior, remote interface correctness, takeover detection, multiplayer safety or long-run stability.
- If a load fails, inspect the specific error/log and correct the tested source; retest using the same save. Do not create extra saves, silently restart/kill unrelated game processes, or auto-approve tools.
- Report exact version, mod set, executed tests, exit results and observed errors; mark untested cases as **not tested**. Request approval before destructive or world-changing actions.
