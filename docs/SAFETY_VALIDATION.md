> Historical safety-only test record. For the current restricted profile and 58-test suite, see [hardening validation](HARDENING_VALIDATION.md).

# Prototype safety validation

Tested October 17, 2026, with Factorio 2.0.77, a disposable single-player world, a separate patched backend and an independent game-state observer.

| Scenario | Result | Observed stop delay |
|---|---|---:|
| Controller Stop request | Passed | 0.125 seconds |
| Controller killed | Passed | 1.797 seconds |
| Backend killed | Passed | 1.719 seconds |
| Backend RCON connection cut | Passed | 1.782 seconds |
| Actual dashboard Stop button | Passed | About 0.20 seconds |
| Actual dashboard Close, confirmed Yes | Passed | About 0.15 seconds after confirmation |

Every final case started with observed movement. The first four cases had zero position drift for 72 further game ticks; the dashboard cases had zero drift for 120 further ticks. Fault cases stopped through the game-side lease. Observed timing includes sampling and UI-injection overhead; it is not a real-time guarantee.

The first four cases used deterministic controller fixtures. Dashboard cases used the actual dashboard, its actual controller and a localhost deterministic model-response fixture. The test player ran slowly in a clear disposable corridor; no main save was used. These tests do not establish performance with a real model, multiple players, paused simulation, or arbitrary modded worlds.

Live testing found and fixed two problems: stop acknowledgement could read the prior walking state within the same game tick, and controller exit during a modal Close confirmation could leave the dashboard waiting for an already consumed exit event. Stop confirmation now retries within the existing 1.5-second budget. Close handles an already exited controller and prevents starting a new session while closing.

All 34 offline tests passed after these fixes. The backend patch compiled against cached local dependencies with no compiler errors; existing ImageSharp dependency vulnerability warnings remain unresolved. Pause/resume, stale-owner requests, manual takeover and repeated stress runs remain live-test follow-ups.

The lease expires after 120 advancing game ticks. Read [setup and limitations](PROTOTYPE_SETUP.md) and the [backend patch instructions](../backend-safety/README.md) before any use.
