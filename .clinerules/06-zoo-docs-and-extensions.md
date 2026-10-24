# Permanent Zoo Code reference and editor workflow

Read all active `.clinerules` files before making project changes. For Lua work, prioritize `04-factorio-lua-references.md` and `05-mod-testing.md`.

- Offline API references are under `.local/factorio-api-offline/2.1.23/files/` (the supported reference); the archived `2.0.77/files/` and `2.1.22/files/` folders are historical comparison material only. See `docs/OFFLINE_FACTORIO_API.md`. Factorio 2.1.23 is the only supported development and testing version.
- Look up real Factorio runtime classes/events in `runtime-api.json`; prototypes in `prototype-api.json`. Use local HTML documentation for lifecycles, storage and migrations.
- Respect `.vscode/settings.json` for Python and Lua diagnostics. VS Code recommendations in `.vscode/extensions.json` do not mean an extension is installed or callable; check first.
- For Factorio Lua: diagnostics plus the appropriate isolated game-load test. For Python: Pylance/interpreter, dependency check, and relevant deterministic tests.
- The active launcher profile is `.local/launcher-profiles/2.1.23/launcher.local.json`. Archived 2.1.22/2.0.77 profiles and saves are preserved for rollback only; do not create additional persistent saves.
- Changes to documentation/rules/configuration alone do not require a game test unless they affect runtime behavior; state the test scope accurately.
- If a required source or tool cannot be read, say so and ask for the missing input rather than guessing.
