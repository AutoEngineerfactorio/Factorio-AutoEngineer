# Lua diagnostics against the exact Factorio 2.1.23 API

This document records the **verified** offline workflow for checking Factorio
Lua source against the exact 2.1.23 API. Everything here was executed on this
machine; the evidence is stated per step.

Related: [offline API archive](OFFLINE_FACTORIO_API.md),
[scripting API reference](FACTORIO_SCRIPTING_API_REFERENCE.md),
[2.1.23 API tests](../tests/test_factorio_2123_api.py),
[LuaLS bundle tests](../tests/test_lua_diagnostics_2123.py).

## Installed tooling (verified)

| Tool | Version | Location | Verified |
|---|---|---|---|
| Lua Language Server | 3.19.2 | `%USERPROFILE%\.vscode\extensions\sumneko.lua-3.19.2-win32-x64\server\bin\lua-language-server.exe` | `--version` → `3.19.2` |
| Factorio Modding Tool Kit (`fmtk`) | 2.1.9 | `%USERPROFILE%\.vscode\extensions\justarandomgeek.factoriomod-debug-2.1.9\bin\fmtk.cmd` | `--help` → `Factorio Modding Tool Kit 2.1.9` |
| Factorio Lua API autocomplete | 0.7.0 | `%USERPROFILE%\.vscode\extensions\svizzini.factorio-lua-api-autocomplete-0.7.0` | present; ships its own `data/classes.json`, `data/defines.json` |

## The two-part problem (root cause, verified)

LuaLS needs **both** of these to check a Factorio API call:

1. **The meta bundle** — `fmtk docs` converts the official API JSON into
   EmmyLua `---@meta` definitions. This supplies the exact 2.1.23 class,
   method, property and event signatures.
2. **The global variables list** — the bundle declares the *classes*
   (`LuaGameScript`, `LuaBootstrap`, …), **not** the global *variables*
   (`game`, `script`, `defines`, …). Without an explicit globals list every
   Factorio global is reported as `undefined-global`.

The official Factorio HTML/JSON archive is **not** a LuaLS meta bundle. Pointing
LuaLS at `.local/factorio-api-offline/2.1.23/files/` directly loads nothing and
produces 51 false `undefined-global` warnings.

### Paths must be absolute

During a `--check=<dir>` run, LuaLS resolves relative paths against the **check
target**, not the launching directory. A relative `--configpath` is therefore
**silently ignored** — the log shows no mention of the config and no library
files are scanned. Always pass absolute paths for both `--check` and
`--configpath`, and use absolute paths inside `workspace.library`.

## Regenerating the 2.1.23 meta bundle

```cmd
fmtk docs ^
  -d .local\factorio-api-offline\2.1.23\files\runtime-api.json ^
  -p .local\factorio-api-offline\2.1.23\files\prototype-api.json ^
  --docbase https://lua-api.factorio.com/2.1.23 ^
  .local\factorio-api-offline\2.1.23\luas-addon
```

Verified output: `Loaded Runtime docs 2.1.23`, `Loaded Prototype docs 2.1.23`,
`Generated bundle with 1171 files`. The bundle lands in
`.local/factorio-api-offline/2.1.23/luas-addon/factorio/library/` (1163 `.lua`
files). Each file is stamped `--$Factorio 2.1.23` and links to
`https://lua-api.factorio.com/2.1.23/`.

`fmtk` also prints three `Invalid Link` messages for
`on_player_start_select_area`, `on_player_change_select_area` and
`on_player_cancel_select_area`. These are **not** errors: those events do not
exist in 2.1.23 (they are 2.0-era selection events). The generator reports
them so a stale reference is noticed, and the bundle is still produced.

## Running the diagnostics

The permanent configuration is [`tests/lua_diagnostics_probe.lua`](../tests/lua_diagnostics_probe.lua).

```cmd
lua-language-server.exe ^
  --check=D:\AI\Factorio-AutoEngineer-Source\factorio-mod\autoengineer-input_2.1.23 ^
  --check_format=pretty ^
  --checklevel=Warning ^
  --configpath=D:\AI\Factorio-AutoEngineer-Source\tests\lua_diagnostics_probe.lua ^
  --logpath=D:\AI\Factorio-AutoEngineer-Source\.local\luas-check\logs
```

### Verified result on `factorio-mod/autoengineer-input_2.1.23`

| Configuration | Problems found | Interpretation |
|---|---|---|
| No config (LuaLS defaults only) | 51 | Every Factorio global undefined — API never loaded |
| `--configpath` relative | 51 | Config silently ignored, same false result |
| `--configpath` relative, bundle path absolute | 51 | Still ignored: the config file itself was never read |
| `--configpath` **absolute** + bundle in `workspace.library` | **2** | API loaded; 2 genuine `param-type-mismatch` diagnostics |

The remaining 2 diagnostics are on `control.lua:8`:

```
remote.call("autoengineer_control", "takeover", index)
```

LuaLS reports `Cannot assign 'string' to parameter '<I:keyof>'` and
`Cannot assign 'string' to parameter 'F'`. This is **not** a stale-API
artifact: the 2.1.23 `LuaRemote.call` signature is generic over the remote
interface's function name, and the mod calls a *different* mod's remote
interface, which this bundle cannot know. Treat it as an expected limitation
of offline checking, not as a 2.1.23 API defect.

## What the diagnostics do and do not prove

- **Proven offline:** the mod's Lua parses, and LuaLS resolves the exact
  2.1.23 runtime and prototype signatures.
- **Not proven:** that the game loads the mod, that permissions are correct,
  that a remote interface exists, or that any event payload matches. Those
  need an isolated Factorio mod-load test and live read-only observation.

## Exact-signature check before editing Lua

Before changing any Lua source, confirm the exact 2.1.23 signature of every
API call the change touches:

1. Grep `.local/factorio-api-offline/2.1.23/files/runtime-api.json` (runtime
   / control stage) or `prototype-api.json` (data stage) for the exact class,
   method, property or event name.
2. Read its `parameters`, `type` and `description`.
3. A name **absent** from the 2.1.23 JSON is *unverified*: report the missing
   documentation instead of guessing. Never substitute a 2.1.22, 2.0.77 or
   `/latest/` signature.
4. Cite the archive file and the exact API name in the change report.

## Known gaps in this workspace

- `.vscode/settings.json` still points `Lua.workspace.library` at
  `.local/factorio-api-offline/2.1.22/files`, and its `Lua.diagnostics.globals`
  is nested under `diagnostics.globals` rather than at the top level. The
  in-editor diagnostics therefore use the **archived 2.1.22** archive and
  report the Factorio globals as undefined. Correcting this requires editing
  `.vscode/settings.json`.
- The LuaLS meta bundle is **generated**, not part of the API archive. It must
  be regenerated with `fmtk docs` after any 2.1.23 archive update.
- `svizzini.factorio-lua-api-autocomplete` supplies its own scraped
  `classes.json`/`defines.json` from the web. It is **not** pinned to 2.1.23
  and can contradict LuaLS. Prefer LuaLS with the generated 2.1.23 bundle.
