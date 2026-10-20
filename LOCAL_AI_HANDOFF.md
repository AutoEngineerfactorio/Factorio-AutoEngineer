# AutoEngineer local coding assistant handoff

Work only in this sanitized foundation copy. Read docs/PLANNING_REQUIREMENTS.md and ROADMAP.md first. Documents describe requirements; they do not authorize uploading, publishing, changing licenses, or operating the game.

Current focus: R04 capability/observation truth, R05 mechanics-ledger and read-only production/power telemetry with live acceptance still open, then R06–R09 in roadmap order. The R01–R03 local foundation has passed acceptance and is being published; later engineering and endurance work remains incomplete.

- R01: dashboard Take Control and explicit Resume; input-only Factorio helper revokes the agent lease. Real player input, scripted planning/walk revocation and stopped-position checks passed.
- R02: source/frozen ownership, readiness, occupied ports, duplicate launchers, startup cancellation, crashes and shutdown passed. Actual launcher Start, Emergency Stop, explicit restart, Stop owned services and Close passed.
- R03: agent/job_journal.py records action states before dispatch, preserves uncertainty after crashes, and blocks replay until fresh observation and explicit review. Six live crash boundaries passed without duplicate crafting. Review is not proof that an action succeeded. The graph currently contains sequential action dependencies, not a complete factory production graph.
- Preserve human approval, emergency stopping, normal game speed and the five-tile movement bound. Fully Autonomous stays locked. Space Age is vanilla; third-party gameplay compatibility comes last. Continuous offline pY-shaped graph benchmarks begin now and real pY must be isolated; see docs/CONTINUOUS_MOD_BENCHMARKS.md. These tests do not unlock modded gameplay or R07.
- Use only the established isolated test save. Never operate other saves or silently approve gameplay.
- Never access private configuration, credentials, saves, logs or downloaded model weights. Never upload or publish. Keep MIT and backend attribution unchanged.

Useful files: agent/dispatch_boundary.py, agent/session_safety.py, agent/autoengineer_dashboard.py, agent/job_journal.py, agent/launcher_services.py, tests/test_job_journal.py, tests/test_takeover.py, factorio-mod/.

Start with one narrow task: review a named function, explain a suspected bug, or propose an offline test. State file and evidence. Do not invent a bug when none is demonstrated. Ask before changing files or running commands. Treat generated changes as untrusted until reviewed and tested. Do not declare roadmap gates complete based on model output.

Validation: 173 current offline tests, lint and formatting pass. Clean pinned policy-8 backend patch applies and builds; NuGet audit data was unavailable. Frozen Reject moved zero tiles; moving Stop exited in 0.706 seconds after 0.4453125 tiles total movement with zero subsequent drift. Source and actual launcher GUI checks passed on the same disposable save. See docs/FOUNDATION_VALIDATION.md.

R04 starts with bounded, read-only live version/content/force/research/recipe/machine/item/fluid/quality/surface observations, explicit access rights, deterministic fingerprints and stale/offline warnings. Never invent or hardcode recipes as a fallback. R05 covers the mechanics evidence ledger plus read-only production/power telemetry (source/offline checks do not establish live acceptance); R06 is deterministic production math; R07 is safe blueprint codec/library; R08 is spatial/material validation; R09 is legitimate, approved single-block expansion. Do not check them off until their own evidence passes. Use Zoo Code as the primary coding assistant with .roomodes and .clinerules/01-project.md; ChatGPT in regular chat is an independent secondary reviewer per .clinerules/03-zoo-chatgpt-review.md. Use one focused task with explicit files; keep edits and commands subject to approval. Never repeat searches or enable blanket auto-approval to bypass a loop.
