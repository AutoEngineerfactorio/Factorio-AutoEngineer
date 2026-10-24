# AutoEngineer coding assurance — researched rules and test matrix

Applies to **ChatGPT, Zoo Code, MiniMax, Copilot**, and future coding agents. Effective immediately for new work; no new tool or dependency installation is authorized by this document.

## Every coding chunk (mandatory)
1. Confirm ownership and avoid overwriting concurrent changes. Name only the files in the chunk guard; cap at two files/200 changed lines unless an explicitly documented exception applies.
2. Capture live VS Code Problems **before** editing: `python -B memory/vscode_problems_gate.py baseline`. If snapshot is missing, stale, incomplete or bridge offline, report **BLOCKED**, not zero Problems. Baseline is ignored local metadata, not a source-of-truth replacement.
3. Use narrow types and validate each external payload at the boundary. Distinguish None/unknown/partial/stale rather than pretending it is valid data.
4. Modify only the authorized files; add or update tests including at least one negative case, and keep the Factorio policy/tool boundary unchanged.
5. Run targeted tests, `python -m ruff check agent tests memory`, and the chunk-guard verification.
6. Allow VS Code to publish **new** language-server diagnostics; run `python -B memory/code_quality_gate.py --stage quick --problems-check`. Fix **all newly introduced errors and warnings**, not the pre-existing baseline. No blanket ignores, analyzer disabling, or fabricated diagnostic exports.
7. Handoff must include original/current VS Code Problems by severity and analyzer, introduced count, tests run, affected files, blocked checks, and evidence. No claim of complete if any required check is blocked.

## Additional gates by changed area
| Area | Required checks |
| --- | --- |
| Python logic | Ruff, Pylance/Pyright nullable/import/type diagnostics; targeted unit tests; malformed payload and timeout paths |
| Factorio Lua | Offline exact-version API verification; LuaLS workspace diagnostics; serialization/permission checks; isolated mod-load verification before live runtime tests |
| C# backend | Pinned clean-upstream patch check, isolated .NET Release build, compiler/analyzer warnings review, no change to 12-tool policy |
| Dashboard/map | Multi-chunk/fog/partial/stale/zoom tests plus actual on-screen screenshot at matching coordinates; runtime observer must remain read-only |
| Telemetry | Compare real game values and units; samples at seconds/minutes; reset, zero-production, disconnected/stale cases |
| Blueprint/planner | Round-trip encode/decode; malformed and deeply nested inputs; technology gating; mods/byproducts/fluids/quality; deterministic calculations |
| Zoo bridge/mobile | Diagnostic API/UI tests, authenticated endpoints, stale/truncated exports, websocket/connect/reconnect/error paths; verify work status is not overwritten by Problems UI |
| All tools | Secrets not logged/staged; no gameplay/save mutation without explicit approval; exactly one persistent test save |

## Before merging/releasing
- Run entire offline unit suite and Ruff; pinned full QA only when the project's pinned environment exists (otherwise label BLOCKED).
- Run isolated backend build for C# changes and relevant mod-load tests for Lua changes.
- Run real Factorio 2.1.23 smoke tests, compare save SHA-256 before/after, confirm policy v8 / 12 tools and safety gates unchanged.
- Verify lint and VS Code diagnostics are **separate independent checks**: a zero-error Ruff run does not imply zero Problems.
- Prefer reproducible, pinned dependencies and restricted CI permissions. No automatically installing or upgrading packages to make a gate pass.
- Never auto-commit or push without user authorization.

## Sources reviewed (official documentation)
- VS Code diagnostics API, global `languages.getDiagnostics()` and `onDidChangeDiagnostics`: https://code.visualstudio.com/api/references/vscode-api
- Pyright type-check rules and configuration, especially optional member/subscript access: https://github.com/microsoft/pyright/blob/main/docs/configuration.md
- Ruff CI and pre-commit integrations: https://docs.astral.sh/ruff/integrations/
- Lua Language Server diagnostics and workspace settings: https://luals.github.io/wiki/settings/
- .NET analyzers, warning severities and warnings-as-errors: https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/overview
- Factorio official staged runtime/prototype API: https://lua-api.factorio.com/
- GitHub Actions secure use, dependency pinning and least privilege: https://docs.github.com/en/actions/reference/security/secure-use

## Agent coding quality workflow (Zoo Code / MiniMax / ChatGPT)
- **Before any coding chunk:** `python -B memory/agent_quality_workflow.py begin`, then open an independently scoped `memory/chunk_guard.py --begin ...` checkpoint. Do not overwrite either baseline halfway through a failed task.
- **After coding and VS Code refresh:** `python -B memory/agent_quality_workflow.py finish`. This runs Ruff, Git diff validation, full offline Python tests, Pyright, VS Code Problems and the quick safety gate. It compares pre/post code hashes; source changes without any changed regression test are blocked.
- **Cross-language / live acceptance:** `python -B memory/layered_quality.py --typing --lua --backend-upstream D:\\AI\\Factorio-AutoEngineer\\FactorioMCP --live --json-output .local/layered-quality-result.json`. LuaLS checks the Factorio 2.1.23 mod and discovers the installed VS Code Lua extension's executable; .NET builds the pinned upstream in an isolated temporary source; `--live` must be explicit and only uses read-only MCP observations. Never execute this live stage against a normal save.
- The core layered runner may be used without cross-language options for ordinary Python chunks. No missing tool is silently passed; diagnostics snapshots missing, stale or truncated block final acceptance. `--skip-problems` is only for bootstrap diagnosis, never final acceptance.
- A portable Windows GitHub Actions workflow lives in `.github/workflows/offline-quality.yml`: fixed tool versions, locked Python dependencies, selected standard-library quality tests, Ruff and Pyright. Its **first GitHub-hosted execution has not been verified**. Full `.local/` Factorio assets and live runtime cannot be assumed on CI runners.
- Zoo mobile companion v4 serves read-only `/api/quality` and shows a quality section next to the existing Problems panel. It exposes only check names and statuses, not source code, secrets or diagnostic file contents; the private proxy requires trusted hosts/Tailscale Serve.
- Quality results are written to ignored `.local/`; `.zoo-diagnostics/vscode-problems.json` continues to be owned by VS Code, never manually fabricated. No gameplay writes, save edits, commits, dependency installs or pushes are authorized by a quality-check command.

## Verified results (2026-10-24)
- Repo-wide Ruff: **0 errors**. Pyright: **0 errors/warnings**. VS Code Problems: **0 errors/warnings**.
- Factorio 2.1.23 LuaLS: **0 problems** after explicit typing of the dynamic remote interface; Lua runtime regression verifies the same calls.
- Isolated pinned .NET backend patch and build: **passed, 0 warnings and 0 errors**. Full Python unit suite: passed.
- Read-only live Factorio map probe: **passed**, observing terrain, resources, natural objects, and visible enemies; save SHA-256 verified unchanged.
- Combined local layered gate: **eight checks passed**. New mobile quality endpoint verified on port 8787.
- Still not demonstrated: GitHub-hosted CI completion, automatic enforcement inside every Zoo/MiniMax task without the agent invoking the wrapper, full game/mod compatibility matrix, and broader security scanning. Label these separately rather than claiming them complete.
