# Permanent Ruff and PowerShell command compatibility

Apply alongside `07-efficient-tool-usage.md`, `08-windows-powershell-environment.md`, and `09-extension-verification.md`.

## Ruff is the canonical Python linter
- Use the configured Python interpreter to invoke `python -m ruff check agent tests --output-format concise`, or invoke verified `ruff` directly.
- Ruff is already a Python linting tool. **Do not report that no Python linter exists** merely because `pylint` and `flake8` are absent.
- Do not install Pylint or Flake8 solely to duplicate Ruff checks. Only request them when a specific test/toolchain requires their distinct functionality.
- Treat Pylance separately: a VS Code language server/type-checking extension, **not** a terminal Python package.
- Run Ruff on changed Python files first, then on the wider `agent` and `tests` directories. Report failures with filename and line; do not change unrelated in-progress files or run mass `ruff --fix` without review.

## Replace Unix head/tail pipes in PowerShell
- Do not use `head -n N` or `tail -n N` in Windows PowerShell.
- File beginning: `Get-Content -LiteralPath 'file' -TotalCount 30`.
- File ending: `Get-Content -LiteralPath 'file' -Tail 30`.
- Bounded command output: `command | Select-Object -First 30` or `command | Select-Object -Last 30`.
- Beware that `Select-Object -First` can terminate an upstream process early; avoid piping long-running tests or installers into it when completion/exit status matters. Capture output and exit status, then inspect bounded results.
- Do not use Bash-only `|| echo` in Windows PowerShell. Run a command, inspect `$LASTEXITCODE` for native executables, and report the actual failure.
- Use targeted reads/searches; avoid repeated `dir`, `Get-ChildItem` across the same directories, and throwaway Python scripts.

## Git working tree safeguards
- An uncommitted or dirty working tree is **not automatically an error**. Identify which changes belong to the current task and whether other Zoo/ChatGPT sessions may be editing them.
- Do not delete or commit all untracked files to make `git status` clean. Stage exact reviewed paths only when explicitly asked to commit.
- Preserve protected assets, secrets, test saves, offline API archives, and prior staging. Do not alter other agents' work.
