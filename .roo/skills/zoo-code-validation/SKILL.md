---
name: zoo-code-validation
description: Review Zoo/Copilot code changes for syntax, patch failures, C# compiler errors, unsafe file staging, tests and retry loops before continuing Factorio AutoEngineer work.
---

# Verified coding skill

Read `.roo/rules/10-verified-coding.md`, `.roo/rules/11-small-verified-chunks.md`, `memory/TEST_README.md` and only the relevant failing file/test. Confirm git status and diff. Make changes through `memory/chunk_guard.py --begin` and `--verify` one bounded, targeted-test-verified chunk at a time; do not overwrite concurrent work.

Use `memory/code_quality_gate.py --stage quick` to inspect changed Python syntax, staged protected filenames and Git whitespace problems. Use `--stage full` for the project offline suite. For backend patch validation and compilation only, use `--stage backend-build --upstream D:\AI\Factorio-AutoEngineer\FactorioMCP`, after checking that upstream is the clean pinned revision. The backend build makes a temporary clone and never touches installed game services.

Require exact command/exit-code evidence; label missing dotnet dependencies as an environment blocker. Repeated failed operation twice means stop and checkpoint. Use second-pass review for realistic Factorio gameplay constraints, failed-run recovery and provider/resource guards. Never claim live game success from offline tests. Keep read-only R07 on hold until the verified pre-R07 checkpoint, keep Semi-Autonomous expansion on hold until Gate H1, and require separate approval for all live actions.
