# Factorio 2.1.23 migration — final validation record

Date: 2026-10-20. Scope: migration cleanup only. No gameplay, no saves, no
RCON, no provider changes, no commit/push/publish, no dependency installs.

Related: [offline API archive](OFFLINE_FACTORIO_API.md),
[scripting API reference](FACTORIO_SCRIPTING_API_REFERENCE.md),
[Lua diagnostics](LUA_DIAGNOSTICS_2123.md),
[API index helper](FACTORIO_API_INDEX_2123.md),
[pending .clinerules patch](CLINERULES_2123_PATCH.md).

## 1. Zoo rules — audited, updates BLOCKED, patch prepared

### Permission limitation (exact)

The `AutoEngineer Code & Review` mode rejects any `.clinerules/` edit:

```
Tool 'edit' in mode 'AutoEngineer Code & Review' can only edit files matching pattern:
^((agent|tests|docs|backend-safety|factorio-mod|packaging|assets|site|website)/.*\.(py|cs|lua|md|json|toml|txt|spec|html|css|js)$|(README|ROADMAP|LOCAL_AI_HANDOFF)\.md$|index\.html$|(handoff|memory)/.*\.(md|json)$|backend-safety/backend-safety\.patch)$
(Project code, website files and safe local handoff/memory notes only).
Got: .clinerules/06-zoo-docs-and-extensions.md
```

`memory/chunk_guard.py` independently refuses the same paths:

```
CHUNK BLOCKED: Path outside permitted source folders: .clinerules/04-factorio-lua-references.md
```

The chunk-guard allowlist at `memory/chunk_guard.py` lines 56-59 was **not**
modified to permit these edits, and no shell redirection was used to write into
`.clinerules/`. `tests/test_clinerules_2123_patch.py` asserts the guard still
excludes `.clinerules/`, so a future widening cannot pass silently.

### Audit result: 15 stale references across the 6 audited files

`git grep -n -E "2\.1\.22|2\.0\.77" -- .clinerules`

| File | Stale references | Nature |
|---|---|---|
| `04-factorio-lua-references.md` | 8 (lines 8, 9, 15-20, 24) | Official URLs pinned to `/2.1.22/` and `/2.0.77/` |
| `05-mod-testing.md` | 2 (lines 17, 18) | Save paths list 2.0.77 and 2.1.22 only |
| `06-zoo-docs-and-extensions.md` | 1 (line 5) | API dirs listed as 2.0.77 + 2.1.22 |
| `08-windows-powershell-environment.md` | 1 (line 21) | API dirs listed as 2.0.77 + 2.1.22 |
| `10-edge-case-handling.md` | 1 (line 23) | "one for 2.0.77 and one for 2.1.22" |
| `15-exa-web-youtube-research.md` | 2 (lines 6, 15) | "Pin Factorio **2.1.22**" plus a `/2.1.22/` query example |

Not in scope and **correctly left alone**: `16-r05-regression-guard.md` (a dated
historical test result) and `17-factorio-2-1-23-primary.md` (which already
states 2.1.23 is the target and labels 2.1.22/2.0.77 as rollback material).

### Patch prepared for an authorized writer

`docs/CLINERULES_2123_PATCH.md` contains the exact **Before**/**After** text for
all six files. Every "Before" block is verified to exist **verbatim** in the
real file by `tests/test_clinerules_2123_patch.py`, so the patch applies
cleanly. The patch:

- repoints every official URL to `/2.1.23/`;
- points the offline API paths at `.local/factorio-api-offline/2.1.23/files/`;
- adds the exact-signature check to `04` and `05`;
- adds the 2.1.23 launcher profile and save, keeping 2.0.77 and 2.1.22
  explicitly labelled **archived**;
- changes **no** approval rule, stop rule, autonomy lock, five-tile bound,
  R07-B item or chunk-guard rule.

## 2. Root documentation — VERIFIED consistent

Independent inspection. These root files are outside the chunk guard's
allowlist, so they were **not** covered by any verified chunk and no
chunk-guard verification is claimed for them.

| File | Line | Statement |
|---|---|---|
| `ROADMAP.md` | 9 | "Factorio AutoEngineer supports Factorio 2.1.23 stable only." |
| `ROADMAP.md` | 26 | "Factorio **2.1.23** is the sole supported development and testing version." |
| `ROADMAP.md` | 27 | 2.1.22 and 2.0.77 are "archived/rollback only" |
| `README.md` | 9 | "**Supported game version: Factorio 2.1.23 only.**" |
| `README.md` | 14 | "FactorioMCP connection to a Factorio **2.1.23** test server (the only supported game version)" |
| `LOCAL_AI_HANDOFF.md` | 2 | "**Factorio 2.1.23 is the only supported development and testing version.**" |
| `LOCAL_AI_HANDOFF.md` | 17 | API reference library paragraph naming the 2.1.23 archive and the exact-signature helper |

All three consistently name 2.1.23 as the only supported version and treat
2.1.22/2.0.77 as archived. **No inconsistency found.**

## 3. Official API documentation — PRESENT locally

The complete official Factorio 2.1.23 Lua API archive exists at
`.local/factorio-api-offline/2.1.23/files/`.

- **Version**: `application_version` `2.1.23`, `api_version` `6` in both
  `runtime-api.json` and `prototype-api.json`. `index.html` declares
  "Version 2.1.23" with the `/2.1.23/` base URL.
- **Size**: 3380 files.
- **Origin**: a verbatim copy of the verified installation's `doc-html` at
  `D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\doc-html`. The enclosing
  folder name is historical; the version was read from the documents.
- **Licence**: the upstream Wube `license.html` with its copyright notice is
  preserved (`Wube` and `Copyright` both present).

### Required files — all present

`index.html`, `runtime-api.json`, `prototype-api.json`, `license.html`,
`index-runtime.html`, `index-prototype.html`, `index-auxiliary.html`,
`events.html`, `classes.html`, `concepts.html`, `types.html`,
`prototypes.html`, `defines.html`.

Required directories — all present: `auxiliary/`, `classes/`, `types/`,
`prototypes/`, `concepts/`, `static/`.

### Machine-readable content (measured)

| Document | Version | api_version | Content |
|---|---|---|---|
| `runtime-api.json` | 2.1.23 | 6 | 157 classes, 229 events, 496 concepts |
| `prototype-api.json` | 2.1.23 | 6 | 279 prototypes, 706 types |

The archived 2.0.77 (3160 files) and 2.1.22 (3379 files) archives are also
complete and are retained as historical comparison material only. **No 2.1.22
signature is used as authoritative for 2.1.23**: the lookup helper
`agent/factorio_api_2123.py` reads only the 2.1.23 archive and refuses any
document whose `application_version` is not `2.1.23`.

## 4. Tests and quality checks — actual exit codes

| Command | Exit code | Result |
|---|---|---|
| `python -B -m unittest discover -s tests -p test_clinerules_2123_patch.py -v` | 0 | Ran 6 tests — OK |
| `python -B -m unittest discover -s tests -p test_factorio_2123_api.py -v` | 0 | Ran 8 tests — OK |
| `python -B -m unittest discover -s tests -p test_lua_diagnostics_2123.py -v` | 0 | Ran 6 tests — OK |
| `python -B -m unittest discover -s tests -p test_factorio_api_index.py -v` | 0 | Ran 11 tests — OK |
| `python -B -m unittest discover -s tests -q` | 0 | Ran 742 tests — OK |
| `python -m ruff check agent tests memory` | 0 | All checks passed! |
| `git diff --check` | 0 | clean (CRLF line-ending warnings only) |
| `python -B memory/chunk_guard.py --verify <id> --test-stage offline` | 0 | CHUNK VERIFIED |

Evidence type: **OFFLINE** only. The pinned `.venv` is still absent, so the
pinned full gate remains **BLOCKED**, not passed. Live Factorio acceptance is
unchanged and still open (R05 Phase 1A, the narrow pre-R07 gate, H1).

## 5. Remaining migration blockers

1. **`.clinerules` not updated** — blocked by the mode's file restriction, not
   by a technical fault. The patch is ready in
   `docs/CLINERULES_2123_PATCH.md` and needs a writer with `.clinerules`
   permission. Until then the six rules still point at the 2.1.22/2.0.77 API.
2. **`.vscode/settings.json` not updated** — `Lua.workspace.library` still
   points at `.local/factorio-api-offline/2.1.22/files`, and
   `Lua.diagnostics.globals` is nested under `diagnostics.globals` instead of
   the top level. **In-editor Lua diagnostics therefore use the archived
   2.1.22 API** and report the Factorio globals as undefined. It should point
   at `.local/factorio-api-offline/2.1.23/luas-addon/factorio/library` with
   `globals` at the top level. This file is also outside the mode's allowlist.
3. **`.roo/rules/12-minimax-provider.md` and
   `.roo/skills/factorio-2123-readonly-qa/SKILL.md`** — need the explicit
   "check the exact 2.1.23 signature before editing Lua" rule. Also outside
   the mode's allowlist.
4. **Live acceptance still open** — the 2.1.23 API archive being complete
   does **not** establish R05 live mechanics acceptance, the R06 production
   math sign-off, the narrow pre-R07 gate or Gate H1. Those remain separate
   and gated.

## Autonomy and safety gates — unchanged

Nothing in this task altered human approval, emergency stop, normal game
speed, the five-tile movement limit, the locked Full Autonomy mode, the
restricted backend tool allowlist, R07-B's existing progress, or the chunk
guard's limits. The one `param-type-mismatch` pair that LuaLS still reports
on `remote.call` is a genuine cross-mod remote-interface limitation of offline
checking, not a 2.1.23 API defect, and was left visible rather than
suppressed.
