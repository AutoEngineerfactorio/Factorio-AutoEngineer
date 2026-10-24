# Exact Factorio 2.1.23 API lookup

`agent/factorio_api_2123.py` is the machine-readable half of the project's
exact-signature rule. Before modifying any Lua source, look the API up there
instead of guessing, and cite the archive file plus the exact API name in the
change report.

Related: [offline API archive](OFFLINE_FACTORIO_API.md),
[Lua diagnostics](LUA_DIAGNOSTICS_2123.md),
[scripting API reference](FACTORIO_SCRIPTING_API_REFERENCE.md).

## Source of truth

The helper reads **only**
`.local/factorio-api-offline/2.1.23/files/runtime-api.json` and
`.../prototype-api.json`, and refuses to load any file whose
`application_version` is not `2.1.23`.

Archived 2.1.22 and 2.0.77 copies are deliberately **not** consulted, so a name
that exists only in an older version is reported as unknown rather than
silently resolving to a stale signature.

## Usage

```python
import sys
sys.path.insert(0, "agent")
import factorio_api_2123 as api

# Classes
api.find_class("LuaGameScript")

# Exact method signature (parameters, types, optionality, order)
api.find_method("LuaGameScript", "take_screenshot")

# Compact signature for reporting; optional params carry a trailing '?'
api.method_signature("LuaGameScript", "take_screenshot")
# -> 'LuaGameScript.take_screenshot(player?, path?, hide_health_bars?, ...)'

# Events and their documented payload fields
api.find_event("on_player_respawned")
api.event_fields("on_player_respawned")   # -> {'player_index', ...}

# Properties
api.find_property("LuaSurface", "name")

# Cheap existence guard before editing Lua
api.has_api("LuaThisDoesNotExist")   # -> False
```

## Fail-closed behaviour

An unknown name raises `api.UnknownApiError` (a `KeyError`) whose message says
the API is **UNVERIFIED** and must be reported rather than guessed:

```
class 'LuaThisDoesNotExist' is not present in the Factorio 2.1.23 offline API
archive. Treat it as UNVERIFIED and report the missing documentation; do not
guess a signature and do not substitute an archived 2.1.22 or 2.0.77 signature.
```

This is the intended behaviour when the upstream documentation does not cover
an API. Report the missing documentation instead of inventing a signature.

## Verification

`python -B -m unittest discover -s tests -p test_factorio_api_index.py -v`
covers the positive lookups and the fail-closed paths, including that a
2.0-era event (`on_player_start_select_area`) does **not** resolve against the
2.1.23 archive while a 2.1.23-era parameter (`hide_health_bars`) does.

The helper performs no network access, starts no Factorio process, and reads no
save. It only reads local JSON files.
