# Offline Factorio API documentation for Zoo Code

The official Wube documentation archives are installed (or installable) at:

- `.local/factorio-api-offline/2.0.77/files/`
- `.local/factorio-api-offline/2.1.22/files/`

These folders are **local-only** and ignored by Git; they should not be included in a mod ZIP or published to the AutoEngineer repository. Preserve the upstream `license.html` and copyright notices.

## Workflow
1. Identify the running Factorio version before choosing a reference. Never mix 2.0 and 2.1 APIs.
2. Read `.local/factorio-api-offline/<version>/files/index.html` for local browser navigation. The archive also contains `runtime-api.json` and `prototype-api.json` for exact signatures, inherited fields, events, and prototypes.
3. Use `runtime-api.json` for `control.lua`, event handlers, state and telemetry.
4. Use `prototype-api.json` for `data.lua`, recipes, technologies, entities and settings-stage definitions where applicable.
5. Use the accompanying HTML auxiliary pages for data lifecycle, mod structure, storage, migrations, debugging, and related topics.
6. For requested API methods, cite the locally inspected file, API name, and exact Factorio version. Never guess a method name or treat a 2.1-only feature as 2.0 supported.
7. Read `docs/FACTORIO_SCRIPTING_API_REFERENCE.md` for project-specific contracts and `docs/CONTINUOUS_MOD_BENCHMARKS.md` for vanilla, Space Age, Space Exploration, and pY test strategy.

Official upstream version selector: https://lua-api.factorio.com/

## Test rules
Run `python -m unittest discover -s tests -p test_factorio_mod_preflight.py -v` before packaging. This only verifies offline source structure and metadata; it is **not** a Lua syntax, game-load, permissions, or compatibility test. Lua syntax check requires a Factorio-compatible parser or actual game load. Use isolated Factorio installations and disposable saves for live acceptance. Do not change the user's main saves or auto-approve actions.


