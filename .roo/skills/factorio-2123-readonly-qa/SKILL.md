---
name: factorio-2123-readonly-qa
description: Validate AutoEngineer R04/R05 catalog, restricted backend, Factorio 2.1.23 telemetry, Lua/mod compatibility and synthetic versus live evidence without unauthorized gameplay.
---

# Factorio 2.1.23 read-only qualification

## Activation
Use for Factorio 2.1.23 catalog/telemetry QA, versioned Lua or backend changes, pre-R07 readiness, read-only live preflight, and continuous pY-shaped benchmarks. This is not a general permission to operate the game.

## Preparation
1. Confirm D:\AI\Factorio-AutoEngineer-Source, Git dirty paths, current writer, and whether a guard lock is active. Preserve prior edits.
2. Read only the task-relevant sections of ROADMAP.md, docs/R04_R06_PRE_R07_ACCEPTANCE.md, docs/PLANNING_REQUIREMENTS.md, docs/HELPER_FIRST_GATE_H1.md and docs/ZOO_CODE_TASK_PROTOCOL.md.
3. Inspect the exact affected source, tests and allowed 2.1.23 API reference. For every touched Lua API call, check the exact name, parameter and return types in `.local/factorio-api-offline/2.1.23/files/runtime-api.json` or `prototype-api.json` (and `agent/factorio_api_2123.py` where suitable). Absent names are UNVERIFIED, not guessed from 2.1.22 or `/latest/`. No guessed Factorio methods, recipes or research state.
4. Separate evidence as OFFLINE, BUILD, LIVE READ-ONLY, GAMEPLAY or NOT RUN. Never promote historical 2.1.22 data into current 2.1.23 live acceptance.
5. If edits are needed, acquire `memory/chunk_guard.py` ownership: MiniMax ordinary work uses `--profile minimax` (3 named files/400 changed lines maximum, 200–300 preferred); local/default uses 2/200. Backend/RCON, guard, game-control, policy, approval and stop-sensitive chunks remain 2 files/200 lines even for MiniMax. Verify focused tests and release each chunk before continuing to the next authorized step.

## Safe offline verification
- For Python: python -B -m unittest discover -s tests -p test_relevant.py -q; then python -B -m unittest discover -s tests -q; python -m ruff check agent tests memory; git diff --check.
- The stage choices for memory/chunk_guard.py --verify are offline, dashboard, safety, reality or a named existing test file. Do not use obsolete skills/learner stages.
- The pinned .venv is currently absent. Use available Python 3.12 for explicitly labeled unpinned offline checks; never silently install or borrow another project's environment.
- For Lua/API: use version-pinned first-party offline documentation and the existing test suite. Source reading or syntax does not establish real mod-load success.
- For backend C#: ensure the pinned upstream revision and restricted source/combined patch agree; reconstruct and compile only an isolated clean temporary clone. Do not alter installed vendor/backend or expand the fixed 12-tool allowlist.
- For pY: label artificial 1k/5k/10k-node graphs as SYNTHETIC, not authentic mod content. Keep any real Pyanodons or Space Exploration profile separately isolated.

## Live read-only gate — require a separately authorized scope
1. Confirm the exact installed 2.1.23 executable version and the isolated launcher profile. The executable may retain Factorio_2.1.22 in its directory name; never identify version by directory alone.
2. Positively identify test processes and disposable save/profile ownership. If unknown, stop. Do not operate normal saves, open secrets, spawn items, issue creative commands, move the player, change research or write through RCON/Lua.
3. Use only the verified restricted adapter. Confirm game version, mods, own force/surface, permissions and source fingerprint; no hidden/fog/private observations.
4. Validate recipe/research/catalog completeness: 1-32 entries per page, 10,000-entry fail-closed cap, 400 KB assembled cap, bounded latency, same-tick identity, page ordering and fingerprint behavior.
5. Validate enabled/disabled/hidden recipe handling, technology unlock effects, exact item/fluid identities, machine-data availability, stale or regressed ticks, disconnect/reconnect and malformed/incomplete pages.
6. Keep production/power telemetry units explicit. Do not mix joules/tick, watts, kilowatts, items/second, items/minute or inventory counts.
7. Stop only processes owned and started by the authorized test; report anything left running. Do not call read-only telemetry a physical-factory proof.
8. Record actual version/force/surface identifiers only to the extent approved, sanitized timings/counts, command exit codes and failure evidence.

## Result and downstream gate
- Report PASS, PARTIAL or BLOCKED separately for R04 source truth, R05 observation, R06 rate/batch mathematics and policy restrictions.
- Fail closed on missing prototype, machine compatibility, research, surface or snapshot evidence. Do not fabricate estimates.
- Read-only R07 codec/preview work can begin only after the narrow R04-R06 data/math/safety pre-R07 gate is independently verified; this does not mark R06, Gate H1, Semi, or Full autonomy complete.
