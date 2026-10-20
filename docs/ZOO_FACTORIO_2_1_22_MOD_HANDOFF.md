# Zoo Code handoff — Factorio 2.1.22 input-helper mod update

**Status:** User requests Zoo Code to continue the AutoEngineer input-helper mod update for **Factorio 2.1.22**. This file is a handoff and scope boundary, not evidence of completed compatibility.

## Before starting
- Work in the **main** VS Code workspace: `D:\AI\Factorio-AutoEngineer-Source`.
- Read the latest Git commit and working-tree status **before editing**. Respect changes left by ChatGPT and any other Zoo task. Do not revert or overwrite them without evidence and permission.
- Read `LOCAL_AI_HANDOFF.md`, `ROADMAP.md`, `.clinerules/01-project.md`, `.clinerules/14-live-vscode-problems.md`, and `docs/CONTINUOUS_MOD_BENCHMARKS.md`. Avoid looping through irrelevant docs.
- A prior repair resolved 275 Pylance diagnostics, and the current Python offline suite passed **425 tests and 134 subtests** with Ruff clean. Verify those numbers again after *your* edits rather than assuming they remain true.
- VS Code Problems are exported to `.zoo-diagnostics/vscode-problems.json` (generated/ignored); diagnose new errors honestly.

## Target and scope
- **Primary runtime target:** Factorio **2.1.22**. Keep **2.0.77** as a separate future compatibility/backport target; do not mix the two installations, profiles, or saves.
- Current input-helper source: `factorio-mod/autoengineer-input_2.1.22/`, with `info.json`, `control.lua`, `data.lua`, `inputs.lua` and `LICENSE`. The mod metadata currently says mod version `2.1.22` and `factorio_version: "2.1"`; **validate these against the exact installed game/API, not assumptions**. Do not automatically change version numbers just to quiet an assertion.
- The earlier 0.1.0 mod folder was removed; do not restore obsolete files unless an explicit compatibility case justifies it.
- BOM was removed from `control.lua` and `data.lua`, and matching isolated test staging files were synchronized because the Lua test interpreter rejected BOM. Preserve UTF-8 without BOM.
- Only update the **AutoEngineer human input guard**: linked controls, human takeover/revocation, multiplayer/player-index handling, runtime lifecycle events, data-stage prototypes, interface compatibility, clean packaging, and strict approval/stop boundaries. Do not turn the helper into a general gameplay automation mod.
- Confirm Factorio 2.1.22's real game version and its **official** runtime/prototype scripting API compatibility. Research release/API changes as necessary; cite exact official doc pages or installed-game evidence. A directory name alone proves nothing.
- Start with **one bounded implementation batch**. Inspect `control.lua`, `data.lua`, `inputs.lua`, `info.json`, and `tests/test_input_helper.py`; report any mismatches. Implement only well-supported, testable repairs. Avoid repeated full-project searches.

## Safeguards / approval
- Preserve **manual human takeover, emergency stop, normal game speed, restricted backend, five-tile safety boundary, locked Full Autonomy**, and read-only AI Helper mode.
- No unapproved gameplay, no writing to real user saves, no change to live profile or mod directories, no downloading pY or installing packages automatically, no cloud publication/push, no credential or private file access.
- Use the isolated test profile and disposable save **only after explicit separate approval** for live Factorio QA.
- Make one narrowly scoped edit/test/diff-review cycle, then stop for review if validation fails twice or official API evidence is missing.
- Require user approval for command execution and edits as configured by Zoo. Do not self-approve via the mobile companion.

## Offline verification targets (before claiming success)
1. Validate `info.json` (dependencies, Factorio major/minor constraints, filename/folder consistency) against the actual supported runtime.
2. Run `python -m pytest -q tests/test_input_helper.py tests/test_factorio_mod_preflight.py tests/test_profile_compatibility.py` and the appropriate version/launcher tests. Do not invent test outputs.
3. Run `python -m pytest -q tests` and `python -m ruff check agent tests` when a change can affect shared code.
4. Check individual Lua files compile/execute in the existing deterministic Lua harness. Do not assume offline Lua execution proves game data-stage or control-stage runtime compatibility.
5. Audit the source mod and isolated staging/profile artifact separately. Keep 2.0.77 assets independent.
6. Report modified files, exact test results, remaining unknowns, and any necessary explicit approval for a **real isolated 2.1.22 game launch**.

**Completion language:** Report "source/offline checks passed" unless a real, correctly identified Factorio 2.1.22 profile was launched and the mod was actually observed loading and functioning there. Do not claim live compatibility from source tests alone.
