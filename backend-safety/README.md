# Backend safety patch

This patch accompanies the supervised Python controller. It was built and tested in a separate backend copy; the original working backend was left unchanged. The upstream backend MIT license is unchanged and reproduced in [third-party notices](../THIRD_PARTY_NOTICES.md). Original AutoEngineer additions use the [project MIT license](../LICENSE). Upstream attribution and provenance review still apply; this patch is not a complete backend distribution.

## Contents

- `backend-safety.patch`: modifies `FactorioService.cs`, `PathfindingService.cs`, and `MovementTools.cs`, and adds `Tools/SafetyTools.cs`.
- `SafetyTools.cs`: readable copy of the new safety tools, already included in the patch. Do not add it twice.
- `BASELINE.json`: source hashes identifying the exact local files used to create the patch. This is not an upstream commit identity.

Use a separate copy of the matching backend checkout. Preserve its license, source and attribution. From that copy, review and check the patch with `git apply --check <path-to-backend-safety.patch>`, then apply it and build `FactorioMCP/FactorioMCP.csproj`. Point the staged controller's ignored local configuration at that copy's rebuilt DLL. These instructions do not authorize publishing the backend or changing its licensing. If the patch does not match, review differences; do not force it onto an unknown revision.

## Design

`autoengineer_arm`, `autoengineer_renew`, and `autoengineer_stop` bypass `GameCommandQueue`; the shared RCON transport still serializes its own connection. Arm installs the guarded tick handler and clears prior movement before granting a lease. It requires exactly one connected character and rejects another active owner's request.

The lease stores a random session identifier, player index, stopped latch and deadline. Renewal requires the same owner and an unexpired, unstopped lease. Stop clears both `storage.walk_dir` and `storage.mine_state`, sets walking/mining false, and returns explicit acknowledgement. A stale owner cannot stop a replacement session.

The game handler denies movement without a live lease, latches expiry, clears automation state and stops the leased player. It only overrides walking/mining when there was an automation direction/state to clear; it does not continuously block manual movement after stopping. Character/player availability is rechecked every tick. Backend path following captures the lease owner and checks it before writing walking directions. `walk_to_position` now requires `safetyOwner`; queued calls from an earlier session cannot borrow a newer lease. Other navigation paths that omit an owner intentionally fail closed.

The Python controller alone calls these tools; their names and parameters are not exposed to the model. This does not prevent a separately authorized raw RCON/MCP caller from bypassing the policy or replacing the handler. RCON is still a privileged channel.

## Verification limits

The patched backend compiled offline against the cached local dependencies with zero compiler errors. The build retained existing ImageSharp dependency vulnerability warnings; no dependency upgrade was attempted in this change. The 34 Python offline tests exercise orchestration and simulated tool responses.

The patch's Lua was subsequently exercised in an isolated Factorio 2.0.77 server with a fresh save and independent observer. Stop, controller termination, backend termination and backend RCON loss all stopped genuine movement and left the player's position stable for 72 further observed ticks. Observed stopping delays were 7, 107, 103 and 107 game ticks respectively. Controller termination and connection loss stopped at lease expiry; explicit Stop received a later-tick acknowledgement. No model service or dashboard GUI was involved; this was a deterministic controller fixture. See the [validation record](../docs/SAFETY_VALIDATION.md) for limits and evidence.

The actual dashboard Stop and confirmed Close controls subsequently passed live tests during movement. Remaining live follow-ups include pause/resume, stale renew/walk/stop requests, manual walking after stop and refusal of an unpatched backend. The expected expiry bound is 120 advancing game ticks; it is not a real-time guarantee. Keep further tests in disposable worlds.
