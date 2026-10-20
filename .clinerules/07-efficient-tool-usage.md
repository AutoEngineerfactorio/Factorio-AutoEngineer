# Permanent efficient file search and tool usage policy

Apply on every AutoEngineer task alongside rules 01-06. These instructions optimize how to find information; they NEVER override safety, approvals, testing, or scope limits.

## Search in the least expensive useful way
1. If a path and file are already known, open/read that exact file or a bounded line range. Do not search the entire repository.
2. For a symbol or literal, search a narrowly scoped folder using ripgrep (`rg`) when available. Example: `rg -n -F 'script.on_event' factorio-mod`. Use `rg --files` to locate filenames.
3. If `rg` is not installed or not callable, use native PowerShell `Get-ChildItem`, `Get-Content`, and `Select-String` with an explicit folder/file scope. Example: `Get-ChildItem factorio-mod -Recurse -Filter '*.lua' -File | Select-String -SimpleMatch 'script.on_event'`. Built-in VS Code search also works.
4. For tracked source, check `git status --short`, `git diff -- <path>`, or `git grep -n -F 'pattern' -- <path>` before inventing other search tools.
5. Search `docs/`, `agent/`, `factorio-mod/`, `tests/` or an exact version's offline API folder separately. Do not scan `.local/` wholesale or recurse through caches, virtual environments, `.git`, models, saves or downloaded dependencies.
6. When searching `.local/factorio-api-offline/<version>/files/`, use the pinned version and the exact HTML/JSON API file relevant to the question; only parse the JSON when its structured data is required.

## Avoid throwaway scripts
- Do NOT create or run one-off Python scripts merely to list files, search for text, read a known file, inspect a few JSON keys, or show a Git diff. Use built-in editor/terminal tools.
- Python is appropriate for substantial structured analysis, reusable production code, deterministic tests, telemetry processing, or complex recipe/technology graph transformations. Prefer an existing script/test over writing a new one.
- Never generate a new helper script as the default fallback after one search-tool failure; use the native command alternative.
- Do not repeatedly issue identical searches. Reuse results from the current task; narrow or change the query only when evidence is missing.
- Keep output concise (matching filenames and bounded surrounding lines). Avoid dumping huge logs, entire JSON archives, or thousands of search hits into model context.
- Temporary helper files require an explicit reason and must be kept out of tracked source unless intended as reusable tooling. Never delete unrelated existing files.

## Efficiency + verification report
For nontrivial implementation work, state which files were located, what native search/read commands were used, and what tests actually ran. Tool preference cannot substitute for a required safety or runtime test. Keep individual approvals and fail-closed behavior intact.
