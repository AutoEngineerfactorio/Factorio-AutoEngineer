# Pending `.clinerules` 2.1.23 updates — for an authorized writer

## Why this file exists

The `AutoEngineer Code & Review` mode **cannot edit `.clinerules/`**. The
attempted edit of `.clinerules/06-zoo-docs-and-extensions.md` was rejected by
the mode's file restriction:

```
Tool 'edit' in mode 'AutoEngineer Code & Review' can only edit files matching pattern:
^((agent|tests|docs|backend-safety|factorio-mod|packaging|assets|site|website)/.*\.(py|cs|lua|md|json|toml|txt|spec|html|css|js)$|(README|ROADMAP|LOCAL_AI_HANDOFF)\.md$|index\.html$|(handoff|memory)/.*\.(md|json)$|backend-safety/backend-safety\.patch)$
(Project code, website files and safe local handoff/memory notes only).
Got: .clinerules/06-zoo-docs-and-extensions.md
```

`memory/chunk_guard.py` independently rejects `.clinerules/` too:

```
CHUNK BLOCKED: Path outside permitted source folders: .clinerules/04-factorio-lua-references.md
```

Neither restriction was bypassed. `memory/chunk_guard.py` was **not** modified
to widen its allowlist, and no shell redirection was used to write into
`.clinerules/`. This document contains the exact edits instead, for a writer
who holds those permissions.

## Scope

Six active rule files. Only version references and API paths change. **No**
safety gate, approval rule, autonomy lock, R07-B progress item or
chunk-guard rule is altered.

The archived `2.0.77` and `2.1.22` folders and the existing persistent test
saves are **preserved as historical facts** — the instructions below keep all
three saves and mark 2.1.22 and 2.0.77 as archived.

---

## 1. `.clinerules/04-factorio-lua-references.md`

Replace the numbered list (lines 5–12):

**Before**

```
## Before writing any Factorio Lua
1. Determine the actual Factorio executable/test profile version and enabled mods; do not assume latest docs match the running game.
2. Select the exact official API version:
   - Stable 2.0.77: https://lua-api.factorio.com/2.0.77/
   - Experimental 2.1.22: https://lua-api.factorio.com/2.1.22/
   - Version list: https://lua-api.factorio.com/
3. Read the relevant official page for each method, prototype, field, and event. The latest URL is useful for discovery, **not authoritative for another installed version**.
4. Consult `docs/FACTORIO_SCRIPTING_API_REFERENCE.md`, `docs/FACTORIO_MECHANICS_REFERENCE.md`, `docs/FACTORIO_QUIRKS_AND_EDGE_CASES.md`, and `docs/CONTINUOUS_MOD_BENCHMARKS.md` for AutoEngineer requirements.
```

**After**

```
## Before writing any Factorio Lua
1. Determine the actual Factorio executable/test profile version and enabled mods; do not assume latest docs match the running game.
2. Use the **exact offline 2.1.23 archive** at `.local/factorio-api-offline/2.1.23/files/`:
   - `runtime-api.json` (runtime/control stage) and `prototype-api.json` (data stage) for exact signatures.
   - `index.html` and the per-class HTML pages for readable documentation.
   - Both JSON files declare `application_version` `2.1.23` and `api_version` `6`.
   - The archived `2.1.22` and `2.0.77` folders are historical comparison material only, never the active contract.
3. Read the relevant official page for each method, prototype, field, and event. The latest URL is useful for discovery, **not authoritative for another installed version**.
4. Consult `docs/FACTORIO_SCRIPTING_API_REFERENCE.md`, `docs/FACTORIO_MECHANICS_REFERENCE.md`, `docs/FACTORIO_QUIRKS_AND_EDGE_CASES.md`, and `docs/CONTINUOUS_MOD_BENCHMARKS.md` for AutoEngineer requirements.

## Exact-signature check before editing Lua
Before modifying any Lua source, confirm the exact 2.1.23 signature of every API call the change touches:
1. Grep `.local/factorio-api-offline/2.1.23/files/runtime-api.json` or `prototype-api.json` for the exact class, method, property or event name.
2. Read its `parameters`, `type` and `description` before writing the call.
3. If the name is absent from the 2.1.23 JSON, treat it as **unverified**: report the missing documentation instead of guessing. Never substitute a 2.1.22, 2.0.77 or `/latest/` signature.
4. Cite the archive file and the exact API name in the change report.
```

Replace the reference map (lines 14–24):

**Before**

```
## Official primary reference map
- Runtime Lua API (control stage): https://lua-api.factorio.com/2.1.22/index-runtime.html
- Prototypes (data stage): https://lua-api.factorio.com/2.1.22/index-prototype.html
- Mod lifecycle: https://lua-api.factorio.com/2.1.22/auxiliary/data-lifecycle.html
- Storage/save/load: https://lua-api.factorio.com/2.1.22/auxiliary/storage.html
- Structure and dependencies: https://lua-api.factorio.com/2.1.22/auxiliary/mod-structure.html
- Auxiliary topics, migrations and JSON schema: https://lua-api.factorio.com/2.1.22/index-auxiliary.html
- Tutorials: https://wiki.factorio.com/Tutorial:Modding_tutorial
- General Lua 5.2 language manual (syntax only; Factorio APIs differ): https://www.lua.org/manual/5.2/

If running Factorio 2.0.77, **replace /2.1.22/ with /2.0.77/** in these official API URLs and verify a matching page exists.
```

**After**

```
## Official primary reference map
Pinned to the supported target 2.1.23:
- Runtime Lua API (control stage): https://lua-api.factorio.com/2.1.23/index-runtime.html
- Prototypes (data stage): https://lua-api.factorio.com/2.1.23/index-prototype.html
- Mod lifecycle: https://lua-api.factorio.com/2.1.23/auxiliary/data-lifecycle.html
- Storage/save/load: https://lua-api.factorio.com/2.1.23/auxiliary/storage.html
- Structure and dependencies: https://lua-api.factorio.com/2.1.23/auxiliary/mod-structure.html
- Auxiliary topics, migrations and JSON schema: https://lua-api.factorio.com/2.1.23/index-auxiliary.html
- Version list: https://lua-api.factorio.com/
- Tutorials: https://wiki.factorio.com/Tutorial:Modding_tutorial
- General Lua 5.2 language manual (syntax only; Factorio APIs differ): https://www.lua.org/manual/5.2/

The archived 2.1.22 and 2.0.77 references remain available under `.local/factorio-api-offline/` for historical comparison only. Do not treat them as the current API.
```

---

## 2. `.clinerules/05-mod-testing.md`

Line 7 — **Before**

```
- Read the local reference at `.local/factorio-api-offline/<version>/files/`: `runtime-api.json`, `prototype-api.json`, and version-specific HTML.
```

**After**

```
- Read the local reference at `.local/factorio-api-offline/2.1.23/files/`: `runtime-api.json`, `prototype-api.json`, and version-specific HTML. The archived 2.1.22 and 2.0.77 folders are historical comparison material only.
```

Line 8 — **Before**

```
- Treat `control.lua` (runtime), `data.lua` (prototype registration), and `settings.lua` (settings stage) as distinct lifecycles. Never guess globals, method signatures, or events.
```

**After**

```
- Treat `control.lua` (runtime), `data.lua` (prototype registration), and `settings.lua` (settings stage) as distinct lifecycles. Never guess globals, method signatures, or events. Confirm the exact 2.1.23 signature of every API call before editing Lua; a name absent from the 2.1.23 JSON is unverified and must be reported, not guessed.
```

Lines 17–20 — **Before**

```
- 2.0.77: `.local/launcher-profiles/2.0.77/data/saves/autoengineer-test.zip`
- 2.1.22: `.local/launcher-profiles/2.1.22/data/saves/autoengineer-test.zip`
- Use the corresponding launcher JSON at `.local/launcher-profiles/<version>/launcher.local.json` and isolated executable. Do not create a third persistent test save or use normal Steam/main saves.
- A mod targeting 2.1 must not be loaded as if it were compatible with 2.0. Test only a verified version-compatible build against 2.0.
```

**After**

```
- 2.1.23 (supported): `.local/launcher-profiles/2.1.23/data/saves/autoengineer-test.zip`
- 2.0.77 (archived): `.local/launcher-profiles/2.0.77/data/saves/autoengineer-test.zip`
- 2.1.22 (archived): `.local/launcher-profiles/2.1.22/data/saves/autoengineer-test.zip`
- Use the corresponding launcher JSON at `.local/launcher-profiles/<version>/launcher.local.json` and isolated executable. Do not create an additional persistent test save or use normal Steam/main saves.
- A mod targeting 2.1.23 must not be loaded as if it were compatible with 2.0. Test only a verified version-compatible build against an archived version, and treat that result as historical rather than current acceptance.
```

---

## 3. `.clinerules/06-zoo-docs-and-extensions.md`

Line 5 — **Before**

```
- Offline API references are under `.local/factorio-api-offline/2.0.77/files/` and `.local/factorio-api-offline/2.1.22/files/`; see `docs/OFFLINE_FACTORIO_API.md`. Choose the one matching the tested executable, not the newest by default.
```

**After**

```
- Offline API references are under `.local/factorio-api-offline/2.1.23/files/` (the supported reference); the archived `2.0.77/files/` and `2.1.22/files/` folders are historical comparison material only. See `docs/OFFLINE_FACTORIO_API.md`. Factorio 2.1.23 is the only supported development and testing version.
```

---

## 4. `.clinerules/08-windows-powershell-environment.md`

Lines 21–22 — **Before**

```
- API docs: `.local/factorio-api-offline/2.0.77/files/` and `.local/factorio-api-offline/2.1.22/files/`
- Launcher profiles: `.local/launcher-profiles/<version>/launcher.local.json`; keep **exactly two persistent test saves**
```

**After**

```
- API docs: `.local/factorio-api-offline/2.1.23/files/` (supported); `2.0.77/files/` and `2.1.22/files/` are archived
- Launcher profiles: `.local/launcher-profiles/<version>/launcher.local.json`; keep **exactly the existing persistent test saves** (2.1.23 supported, 2.0.77 and 2.1.22 archived) and create no new one
```

---

## 5. `.clinerules/10-edge-case-handling.md`

Line 12 — **Before**

```
- Pin installed executable and enabled mod set before using API definitions. Fail closed on missing/renamed runtime fields, removed events, type/nullable changes, version-gated quality/platform/planet functionality and 2.0 vs 2.1 divergence.
```

**After**

```
- Pin installed executable and enabled mod set before using API definitions. Fail closed on missing/renamed runtime fields, removed events, type/nullable changes, version-gated quality/platform/planet functionality and 2.0 vs 2.1 divergence. The supported target is 2.1.23; treat any 2.0/2.1.22 API name as historical and unverified for the current build.
```

Line 23 — **Before**

```
- Preserve exactly two existing persistent test saves, one for 2.0.77 and one for 2.1.22. Use version-specific launcher profile, isolated mod directory, and correct executable; no Steam/main-save writes.
```

**After**

```
- Preserve exactly the existing persistent test saves: the 2.1.23 save is supported, and the 2.0.77 and 2.1.22 saves are archived rollback material. Use the version-specific launcher profile, isolated mod directory, and correct executable; no Steam/main-save writes and no new persistent save.
```

---

## 6. `.clinerules/15-exa-web-youtube-research.md`

Line 6 — **Before**

```
1. Read the matching version-pinned local Factorio API docs and relevant project notes before searching the web. Favor official `lua-api.factorio.com`, `wiki.factorio.com`, `factorio.com`, and primary source repositories for API facts. Pin Factorio **2.1.22** for current implementation, and check **2.0.77** separately. Do not apply obsolete APIs from another version.
```

**After**

```
1. Read the matching version-pinned local Factorio API docs and relevant project notes before searching the web. Favor official `lua-api.factorio.com`, `wiki.factorio.com`, `factorio.com`, and primary source repositories for API facts. Pin Factorio **2.1.23** for current implementation; the local archive is `.local/factorio-api-offline/2.1.23/files/`, and **2.1.22** and **2.0.77** are historical comparison material only. Do not apply obsolete APIs from another version.
```

Line 15 — **Before**

```
- `site:lua-api.factorio.com/2.1.22 LuaFlowStatistics get_flow_count surface force`
```

**After**

```
- `site:lua-api.factorio.com/2.1.23 LuaFlowStatistics get_flow_count surface force`
```

---

## Applying the patch

Apply the six edits with a normal editor, then confirm no stale reference
remains in the active rules:

```cmd
git grep -n -E "2\.1\.22|2\.0\.77" -- .clinerules
```

Every remaining hit must be either an explicitly **archived** reference or a
comparison mention. No line may present 2.1.22 or 2.0.77 as the current API.

`tests/test_clinerules_2123_patch.py` verifies that every "Before" block above
still matches the target file verbatim, so this patch cannot silently drift.
