# Permanent workspace shell and diagnostics rule

Zoo Code operates inside the VS Code workspace `D:\AI\Factorio-AutoEngineer-Source` using Windows PowerShell. Follow rules 07, 08, 09, and 11.

## Stop repeated cd commands
- Determine the current directory once using `(Get-Location).Path` only if truly unknown.
- In VS Code's workspace terminal, use workspace-relative paths directly: `Get-Content agent/dashboard_feed.py`, `git status --short`, `python -m ruff check agent tests`.
- Do not prepend `cd D:`, `cd D:/AI/Factorio-AutoEngineer-Source`, or `Set-Location` to every command. If the terminal is already at the repository root, remain there.
- A new terminal/session may start elsewhere. In that case, change directory **once per session** with `Set-Location -LiteralPath 'D:\AI\Factorio-AutoEngineer-Source'`, then reuse the session. If shell state is not persistent, prefer absolute file paths or the tool's working-directory option when supported.
- Never chain `cd D:` redundantly. A PowerShell command invocation may have a distinct working directory; check it only when a command fails because of location, not by habit.

## Inspect actual Problems diagnostics
- When asked to fix VS Code Problems, first inspect the VS Code Problems panel, grouped by source/file and diagnostic code, or an actual VS Code language-service diagnostic export if available.
- Do not equate Ruff errors with all Pylance/LuaLS/C# diagnostics. Distinguish errors, warnings, and info; report totals by analyzer.
- Fix the highest-impact root causes (wrong interpreter, erroneous configuration, repeated type issues) first; then diagnose each file in bounded batches.
- Do not hide diagnostics, apply blanket ignores, mass-fix concurrent code, or claim all Problems cleared without a fresh panel/diagnostic check.
- If the Problems panel is inaccessible to the agent, ask for an export/screenshot or report the limited data from CLI analyzers honestly. Avoid recursive directory listings and improvised Python scripts to approximate it.
