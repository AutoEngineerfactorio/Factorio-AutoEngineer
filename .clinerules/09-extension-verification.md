# Permanent extension-aware verification

Apply alongside rules 01-08. First classify a named tool before testing it: **VS Code extension**, **shell executable**, **Python package**, **language server**, **Factorio mod**, or **project script**. A tool can span categories but each has a different validation method.

## Verify using the correct interface
- **VS Code extension:** check installed extension ID and enabled state in the appropriate VS Code profile/window; inspect Extensions view and extension Output/logs where available. Installation alone does not prove activation, language service readiness, diagnostics, or access to extension commands.
- **Pylance:** `ms-python.vscode-pylance` is a VS Code extension. Do not run `python -m pylance` or infer failure from a missing terminal command. Inspect Pylance/Python Language Server status and per-file diagnostics. Verify the selected interpreter and imports separately using that interpreter. Never hide `reportMissingImports` to make diagnostics appear green.
- **Python extension:** `ms-python.python`; verify actual interpreter selection, environment and dependencies. A package available in one Python interpreter may be absent from a virtual environment.
- **LuaLS:** `sumneko.lua` runs from its installed extension; `lua-language-server` missing on PATH does not prove extension failure. Check VS Code Lua diagnostics and server logs; if needed, locate bundled executable once using a scoped extension search.
- **Factorio Modding Tool Kit:** `justarandomgeek.factoriomod-debug` is an extension, not a standalone CLI guarantee. Verify configuration and actual debugger/validation invocation separately; do not claim debugger tests without running them.
- **Factorio Lua API autocomplete:** `svizzini.factorio-lua-api-autocomplete`; check for overlapping or contradictory LuaLS completion/diagnostics and pin versions of references.
- **CLI / Python package / mod:** verify with its native command or correct executable/interpreter/isolated Factorio mod-load test, not a generic `--version` guess.

## Handling verification failures
1. Check the right VS Code user-data/profile and workspace; extension installed globally may not be active in an isolated Zoo window.
2. Check whether terminal PATH differs from extension-host PATH.
3. Report separately: installed, enabled, activated, diagnostics working, and live action tested. Use **unknown** if not verifiable.
4. Do not reinstall, change global PATH, switch interpreters, or disable lint/type diagnostics without evidence and approval.
5. Prefer one targeted check over repeated `dir`, Python scripts, Linux shell syntax, or exhaustive extension-folder traversal.

Known workspace instructions: `.vscode/settings.json`, `.vscode/extensions.json`, `docs/OFFLINE_FACTORIO_API.md`, and rules 07-08.
