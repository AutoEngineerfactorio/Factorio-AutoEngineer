# Permanent Windows PowerShell execution and discovery policy

This project is developed on **Windows 11**, with **PowerShell** as the default terminal. Apply this rule with `07-efficient-tool-usage.md` on every Zoo Code task. Existing safety and approval requirements remain unchanged.

## Native commands first
- Do not emit Bash-specific command chains such as `cmd || echo failure`, `grep | head`, `find /path`, or `ls -la` in PowerShell. Use native PowerShell syntax and handle errors explicitly.
- For known files, use `Get-Content -LiteralPath 'path' -TotalCount 80`; for targeted text use `Select-String -LiteralPath 'path' -SimpleMatch 'symbol'`.
- For tracked source prefer `git ls-files`, `git grep -n -F 'symbol' -- path`, `git diff -- path`, and `git status --short`. Note `git grep` excludes untracked files.
- Prefer `rg -n -F 'symbol' path` when `rg` actually exists. Otherwise use a **bounded** `Get-ChildItem -LiteralPath 'folder' -File -Filter '*.lua' -Recurse | Select-String -SimpleMatch 'symbol'`. Do not install `rg` solely to do a routine lookup.

## Avoid repetitive directory discovery
- Before running `dir`, `Get-ChildItem`, or `ls`, ask: is the exact path already in these rules, the current task, or prior command output? If so, use it directly.
- List any directory **at most once per distinct question**. Reuse results; do not keep listing the same location to check progress. When progress matters, check the known file or process directly.
- Do not list the repository root or scan downloaded API docs, `.local`, models, virtual environments, `.git`, saves, or extension directories recursively to locate a known file.
- Limit output (file type, path, and `Select-Object -First N` where appropriate). Avoid full JSON, logs, and unbounded recursive output.
- Do not work around inefficient `dir` usage by generating throwaway Python scripts.

## Known workspace and tooling paths
- Repository: `D:\AI\Factorio-AutoEngineer-Source`
- Project rules: `.clinerules/`; offline reference instructions: `docs/OFFLINE_FACTORIO_API.md`
- API docs: `.local/factorio-api-offline/2.1.23/files/` (supported); `2.0.77/files/` and `2.1.22/files/` are archived
- Launcher profiles: `.local/launcher-profiles/<version>/launcher.local.json`; keep **exactly the existing persistent test saves** (2.1.23 supported, 2.0.77 and 2.1.22 archived) and create no new one
- Python interpreter: `C:\Users\porte\AppData\Local\Programs\Python\Python312\python.exe`, unless `.vscode/settings.json` has been updated after verification
- LuaLS is installed as the `sumneko.lua` VS Code extension. A missing `lua-language-server` executable on PATH does **not** establish a missing or broken extension. Check the installed extension location once, if necessary.

## Command failures and approvals
- First identify whether the failure is shell syntax, missing PATH entry, permissions, wrong directory, or a genuine missing dependency. Retry with one targeted correction, not repeated directory searches.
- If the command requires approval, obtain that specific approval. Never enable blanket auto-approval, expand permissions, or bypass sandbox restrictions.
- Explain genuine blockers and distinguish verification done inside VS Code from standalone terminal checks.
