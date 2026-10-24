# Offline Factorio API documentation for Zoo Code

**Supported game version: Factorio 2.1.23 only.**

The official Wube documentation archives are installed (or installable) at:

- `.local/factorio-api-offline/2.1.23/files/` (the supported reference)
- `.local/factorio-api-offline/2.0.77/files/` and `.local/factorio-api-offline/2.1.22/files/` (archived references, for historical comparison only)

These folders are **local-only** and ignored by Git; they should not be included in a mod ZIP or published to the AutoEngineer repository. Preserve the upstream `license.html` and copyright notices.

The 2.1.23 archive is a verbatim copy of the `doc-html` directory shipped with the
verified isolated installation at `D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\doc-html`
(the enclosing folder name is historical; the executable is verified 2.1.23). Its
`runtime-api.json` and `prototype-api.json` both declare `application_version` `2.1.23`
and `api_version` `6`.

## Workflow
1. Identify the running Factorio version before choosing a reference. The supported target is 2.1.23; archived 2.0 and 2.1.22 references are historical only and must not be used as the active API contract.
2. Read `.local/factorio-api-offline/<version>/files/index.html` for local browser navigation. The archive also contains `runtime-api.json` and `prototype-api.json` for exact signatures, inherited fields, events, and prototypes.
3. Use `runtime-api.json` for `control.lua`, event handlers, state and telemetry.
4. Use `prototype-api.json` for `data.lua`, recipes, technologies, entities and settings-stage definitions where applicable.
5. Use the accompanying HTML auxiliary pages for data lifecycle, mod structure, storage, migrations, debugging, and related topics.
6. For requested API methods, cite the locally inspected file, API name, and exact Factorio version. Never guess a method name or assume an archived-version feature is supported by 2.1.23.
7. Read `docs/FACTORIO_SCRIPTING_API_REFERENCE.md` for project-specific contracts and `docs/CONTINUOUS_MOD_BENCHMARKS.md` for vanilla, Space Age, Space Exploration, and pY test strategy.

Official upstream version selector: https://lua-api.factorio.com/

## Exact-signature check before editing Lua

Before modifying any Lua source, confirm the exact 2.1.23 signature of every API
call the change touches. Do not infer a signature from an archived 2.1.22 or 2.0.77
archive, from memory, or from a `/latest/` web page.

1. Grep the 2.1.23 `runtime-api.json` or `prototype-api.json` for the exact class,
   method, property or event name and read its `parameters`, `type` and `description`.
2. If the name is absent from the 2.1.23 JSON, treat it as **unverified** and report
   it rather than guessing. Do not introduce a call that cannot be checked offline.
3. Cite the archive file and the exact API name when reporting the change.

## Test rules
Run `python -m unittest discover -s tests -p test_factorio_mod_preflight.py -v` before packaging. This only verifies offline source structure and metadata; it is **not** a Lua syntax, game-load, permissions, or compatibility test. Lua syntax check requires a Factorio-compatible parser or actual game load. Use isolated Factorio installations and disposable saves for live acceptance. Do not change the user's main saves or auto-approve actions.

Run `python -m unittest discover -s tests -p test_factorio_2123_api.py -v` to confirm the
offline archive is the exact 2.1.23 API: the archive's declared version, its class,
event, prototype and type counts, the upstream Wube license notice, and byte equality
with the installed 2.1.23 `doc-html` whenever the isolated installation is present.

## Lua diagnostics against 2.1.23

The archive is not itself a Lua Language Server meta bundle. To get LuaLS to
resolve exact 2.1.23 signatures, generate the bundle with `fmtk docs` and point
LuaLS at `.../2.1.23/luas-addon/factorio/library`. The verified workflow, the
absolute-path requirement, the installed tool versions and the observed results
are recorded in [docs/LUA_DIAGNOSTICS_2123.md](LUA_DIAGNOSTICS_2123.md).

Run `python -m unittest discover -s tests -p test_lua_diagnostics_2123.py -v` to
confirm the generated bundle still corresponds to 2.1.23 and is not a stale
2.1.22/2.0.77 bundle.
