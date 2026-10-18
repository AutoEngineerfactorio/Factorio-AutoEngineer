# Normal-speed movement and hosting

The current combined backend patch requires policy **7**. Reapply it to a clean checkout of the pinned upstream revision and rebuild as described in [prototype setup](PROTOTYPE_SETUP.md). The agent rejects older backend policies.

## Movement behavior

The game tick handler steers validated routes using Factorio's sixteen walking directions and a small heading-change penalty. It uses the character's actual running speed; movement does not reduce that speed. The backend bounds requested distance, planned route length, cumulative physical travel and displacement to five tiles. It reserves room for the next tick and stops short if necessary. Some exact-five-tile requests may therefore stop safely or be rejected rather than reach the endpoint.

Arrival is checked against the actual position after walking stops. A passed waypoint projection alone cannot report success. Missing leases, lost ownership, changed surfaces, stalled movement and deadlines stop navigation. Cleanup checks the route ID and owner so an old session cannot cancel a later one. Failed path validation participates in failed-target recovery and requires a fresh approved proposal.

Emergency stopping, the one-use approval boundary and the locked Fully Autonomous mode remain active. The movement patch does not grant the model permission to approve its own actions.

## Visual behavior in multiplayer

Scripted walking on a joined multiplayer client can conflict with client movement prediction, causing visual jitter or a backward correction even when authoritative positions are stable. Server telemetry alone cannot verify visual smoothness.

The same isolated test save was moved from a dedicated server plus joined client to a graphical multiplayer host. The user confirmed no snap-back; five additional normal-speed moves each stopped with no later position drift and no reset between them. This verifies the observed local-host setup, not smooth rendering for every remote multiplayer client.

Factorio supports graphical-host RCON through the private configuration's `[other]` keys `local-rcon-socket` and `local-rcon-password`. Bind RCON to loopback and keep its password out of source control. Write INI key/value pairs without spaces around `=`. The private test configuration is not part of the project package. Command-line RCON flags alone did not enable RCON in the tested graphical-host setup.

## Validation

The separate patched backend builds without warnings or errors. The 130-test Python suite passes, including exact Lua tick execution for normal and elevated speeds, corners, physical travel bounds, stuck movement, owner/surface changes, lease expiry, Stop and heading stability. The optional offline Lua tests use `tests/requirements-lua.txt`; Lupa is not an application dependency. Patch application was verified against clean pinned upstream, with the patched movement sources matching the separate tested backend.

Repeated longer Qwen/Phi trials are recorded separately; do not interpret the earlier interrupted or reduced-speed diagnostics as final normal-speed model results. Phi-4-mini is now the default following the paired trials; Qwen remains configurable.

References: [Factorio staff on scripted walking and prediction](https://forums.factorio.com/viewtopic.php?t=63415), [graphical-host local RCON settings](https://forums.factorio.com/viewtopic.php?t=31962).
