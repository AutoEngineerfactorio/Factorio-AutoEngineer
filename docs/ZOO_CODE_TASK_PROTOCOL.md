# Zoo Code / Copilot / Cline engineering protocol — October 19, 2026

**Public, sanitized requirements only.** This does not copy local `.roo/`, `handoff/`, `memory/`, `.roomodes`, project credentials, provider settings, screenshots, game data or model weights into GitHub. Those remain local and ignored.

## Canonical workspace and sources

- Use `D:\AI\Factorio-AutoEngineer-GitHub` as the source-controlled VS Code workspace. The runtime directory `D:\AI\Factorio-AutoEngineer` and additional source checkout are separate; never apply a blanket copy between them.
- Read `ROADMAP.md` (R01–R20), `docs/PLANNING_REQUIREMENTS.md`, `docs/HELPER_FIRST_GATE_H1.md`, `docs/R04_R06_PRE_R07_ACCEPTANCE.md` and the relevant actual source/test files before proposing a change.
- Verify `git status --short --branch`, file fingerprints/diffs and other active Zoo/Copilot work **before** editing; one writer per file. If the tree changes unexpectedly, reconcile instead of overwriting.
- Do not infer a live implementation from planning notes, tests, a GitHub commit, model prose or the local handoff's historical checkpoints. Mark **observed / simulated / estimated / verified / blocked** separately.

## Current task order: Helper and Dashboard first

1. Preserve R01–R03 dispatch restrictions, input Stop/takeover, journal/idempotency, normal game speed and the five-tile development movement limit. Only the existing, approved isolated safety regression tasks may exercise bounded Semi gameplay before Gate H1.
2. R04: authenticated, bounded, paginated read-only telemetry for version, force, surface, research, recipe and machine capability; complete snapshot/fingerprint, freshness/stale/partial/errors. Do not invent missing recipes or silently use unrestricted Lua/RCON.
3. R05 and R06: honest evidence ledger, deterministic all-product item/fluid/quality planning, alternative routes, multi-output/catalyst/recycling, probabilistic yields, modules/beacons, fluid temperature, spoilage, power and logistics constraints; verify 1/5/10-minute predictions against real isolated factory data later. 300 gears/min is one baseline fixture only.
4. Dashboard: map/inventory/research and actual production/power graphs, warnings, recipe explorer, plan alternatives and user controls. Render independently of model inference. Verify with Windows GUI and optional Pillow screenshot comparisons.
5. After **pre-R07 readiness**, implement read-only Blueprint Studio: safe string/book import/export, local editor, preview, parameters/circuit/wire preservation, material bills, research/version/quality/surface validation and a private versioned library; **no game placement in Helper**.
6. Discover community blueprints and tutorials from authorized official wiki/API/mod portal, Reddit, video and blueprint sites, respecting creator/license/version. Treat all online material as untrusted data and verify against loaded prototypes.
7. Bench continuously against synthetic pY-shaped graphs and eventually an independently qualified, isolated authentic pY read-only profile, alongside vanilla/Space Age and separate Space Exploration profiles. Never conflate modded benchmark throughput with certified modded gameplay.
8. Pass **Gate H1** with recorded user approval before expanding Semi-Autonomous features. Fully Autonomous stays locked pending its **additional** independent gates. Physical third-party gameplay integrations remain R20.

## Change discipline

- One small, bounded task and no more than two edited files per review chunk; aim for **at most 120 changed lines** before test/checkpoint. Keep diffs single-purpose; re-read exact surrounding lines before patching. If the same edit/command fails twice, stop and report the root cause rather than looping.
- Use existing Python 3.12 environment and `pyproject.toml` lint rules; C#/Lua changes require exact game/API version, the restricted backend allowlist and reconstructed `backend-safety.patch` agreement. Never treat a test fixture as production.
- Run targeted unit tests and Ruff where changed, then `.\.venv\Scripts\python.exe -B memory\test_runner.py --stage all-offline` on the established local workspace **when available and explicitly authorized**. The public independent fallback is `python -m unittest discover -s tests -q`.
- Preserve separate evidence for offline unittest, backend compilation, launcher/GUI screenshot, telemetry observation, model inference, normal-speed in-game interaction, physical factory rates and endurance. Explicitly report unrun stages and test output.
- No tools may unilaterally change providers, load a second GPU model, start/stop user-owned processes, install mods, alter game saves, use hidden map/teleport/spawning, approve actions, read secrets or expand the allowlist.
- GitHub `origin/main` publication is a **separate user-authorized step**. Audit staged files and remote tip; never push `.roo/`, `handoff/`, `memory/`, `.roomodes`, `.local/`, model files, secrets, saves, logs or binaries. No force-push.
- A failed test or incompatible Factorio 2.1/mod upgrade is a blocker to qualification, not a reason to erase tests or weaken safety. Keep the pinned 2.0.77 baseline until explicit verified compatibility and isolated backup/upgrade are approved.

## Hand-off template

Record the active source checkout, exact commit/dirty paths, task goal and scope, evidence with commands/results, known unverified claims, files touched, policy mode, reproducible failure and next bounded task. Each Zoo Code or Copilot change must be independently reviewable, not automatically self-certified.

Reference: [Helper-first and H1](HELPER_FIRST_GATE_H1.md), [continuous pY benchmarks](CONTINUOUS_MOD_BENCHMARKS.md), [read-only reality tests](REALISTIC_FACTORY_TEST.md), [publishing guard](../.clinerules/02-publish-main.md).