# Three operating modes

## Behavior
- **AI Helper** is the default. The map and main inventory remain live, independently of AI execution. No gameplay session can start, even if its Python entry point is called directly. Recipe calculators and blueprint design remain future work; this milestone provides permission enforcement and observation only.
- **Semi-Autonomous** requires a visible confirmation when selected. Existing Navigate/Mine/Craft tasks retain fresh per-action approval, owning safety leases, five-tile movement and bounded starter batches. Switching to Helper immediately disables approval and requests game-side stopping; a new Semi session waits for the old child to exit and for stop acknowledgement.
- **Fully Autonomous (locked)** is visible but cannot be selected for execution. Python and backend startup reject Full and unknown values. No unattended gameplay path is implemented.

Mode and task are separate controls. The observer always launches with Helper permissions. Stopping AI leaves it running; closing the dashboard shuts down the owned observer normally. Emergency owner-checked cleanup remains allowed in Helper, including during a switch from active Semi work.

## Enforcement and setup
Rebuild the current combined backend patch. Policy v6 reports the fixed process mode and five-tile limit; the host refuses a mismatch. Python freezes session permissions; the backend request filter independently denies walking, starter operations, lease arm and renewal outside Semi, including direct raw MCP calls. Existing read schemas and owner checks remain in force. Session mode cannot be upgraded by the model or a tool argument.

The dashboard defaults to Helper and explicitly sets the child's mode after the user selects Semi. For direct supervised CLI use, explicitly set `AUTOENGINEER_MODE=semi` along with the existing private RCON environment and local configuration. Missing mode defaults to Helper, which performs no gameplay session. `AUTOENGINEER_MODE=full` and unknown values fail closed. `AUTOENGINEER_BACKEND_MODE` is the backend's fixed internal launch setting, forwarded from the validated host mode; it is not a model option.

No new dependency, license or save migration is required. Do not use an older policy-v5 backend for Semi sessions. Local settings remain ignored; never put credentials into example configuration.

## Validation — 2026-10-18
- 122 offline tests pass, including Helper writes/approval denial, read and Stop allowance, immutable mode, Full/unknown refusal, policy-mode mismatch, locked UI choice, confirmation, stale approval denial, switch cancellation and old emergency-stop/navigation regressions.
- Separate mode-aware .NET backend builds; combined patch applies to clean pinned upstream and reproduces tested sources. NuGet vulnerability metadata was unavailable (NU1900); dependency versions were not changed.
- Python-only integration used real Tk widgets in a withdrawn test window and the same dedicated disposable save. No computer-control tools were used.
- Raw MCP Helper calls to arm, renew, walk and operate were denied; read-only view and owner-checked Stop remained available.
- Helper live ticks advanced without an AI child. Full stayed locked. Semi Reject stopped safely. Switching to Helper while approval was pending cancelled the child, rejected late approval and retained the observer.
- Actual Tk Approve and Stop widget commands were invoked through Python: approved slow mining became active, Stop acknowledged, mining false, craft queue empty and zero movement. Temporary test speed was restored. The observer closed cleanly.
- Raw Semi six-tile movement was independently rejected by the backend, with zero movement and Stop acknowledged.
- Full and invalid backend modes refused before MCP startup. The original five-tile validator and game-side emergency lease/stop implementation are unchanged.

This milestone provides the tested operating-mode foundation. Full autonomy, broad recipe planning, takeover by simultaneous independent characters and exhaustive long-run arbitration remain outside this milestone. This is a constrained application interface, not an OS sandbox against trusted local code or other administrative RCON clients.
