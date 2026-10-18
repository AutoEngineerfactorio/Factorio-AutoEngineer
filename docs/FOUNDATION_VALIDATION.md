# R01–R03 foundation validation — 2026-10-18

Test profile: Windows x64, Factorio 2.0.77 graphical multiplayer host, one connected character, the established isolated test save on Nauvis. The input-only helper is enabled only in that test profile. Game speed remained 1 and the character speed modifier remained 0. Main saves were not selected. Emergency stopping, human approval and the backend five-tile movement boundary remain enabled; Fully Autonomous remains locked.

## Confirmed checks

- **Real player input:** the input generation advanced from 38 to 41, the active AI lease was revoked, and no drift occurred after the player released movement. The test deliberately permits normal human movement after relinquishing AI control.
- **Scripted takeover integration:** revocation during planning rejected a late movement dispatch; revocation during an actual walk stopped owned activity with zero subsequent drift. The inactive handler no longer suppresses human walking.
- **Crash checkpoints:** separate disposable workers were killed at approval-pending, approved, executing-before-write, executing-after-write, observed, and verified. Pre-dispatch interruptions crafted nothing. Completed external writes crafted exactly one gear. Uncertain states required fresh review, including after changing model identity; no action was automatically replayed. Recovery review acknowledges uncertainty rather than proving success.
- **Service ownership and recovery:** another launcher was refused by the profile lock; attached game/model processes survived Stop owned services. Model and game crashes paused service supervision without automatic restart. Explicit restart restored the same test save and live observation.
- **Actual frozen launcher GUI:** Start reached policy-8 backend and fresh Helper observation; Emergency Stop closed the dashboard while preserving the stopped game and model; explicit Start restored observation; Stop launcher-owned services saved and closed owned services; saved ZIP integrity passed; Close exited the launcher.
- **Source regression:** 173 offline tests pass, including real child-process failure during readiness, cancellation during readiness, occupied-listener detection, helper bindings, strict telemetry types, exact approvals, job locking and interrupted-write recovery. Ruff lint and formatting checks pass.
- **Backend reconstruction:** the combined policy-8 patch applies cleanly to the pinned upstream revision and builds successfully. The dependency lock is preserved. NuGet vulnerability-data retrieval was unavailable (NU1900), so this run does not establish a fresh vulnerability audit.

The packaged worker separately exercises an actual approval prompt, Reject without movement and in-motion Stop within the five-tile bound. The final repeat's measured results are recorded with the local acceptance report.

## Corrections found during testing

The launcher now avoids writing through another process's profile lock and tests occupied model ports by exclusive binding. Startup recovery can read `autoengineer_view` through the closed read allowlist. The uncertain-action review dialog lists every action it acknowledges. These checks exercise production code; model-generated review text is advisory evidence only.

The first physical-input fixture incorrectly sampled drift while human movement was still active. It now waits for release before comparing stationary positions. Initial frozen-fixture failures also exposed the missing startup read permission; that defect was fixed before repeating the packaged checks.

## Scope

For the full offline suite, install both the normal pinned runtime dependencies and `tests/requirements-lua.txt`; Lua-specific tests explicitly skip if that optional test dependency is absent. `requirements-dev.txt` pins the formatter/linter used for these checks.

This is a local one-folder foundation prototype using existing installed prerequisites. It is not clean-PC certification, a signed installer, Space Age qualification, a multi-block production planner, or a completed long-duration autonomy test. Durable jobs currently contain a persistent goal and sequential action dependencies; later production planning expands the graph. No new release was published and no license was changed. Space Age remains vanilla scope, and third-party gameplay mods remain last.
