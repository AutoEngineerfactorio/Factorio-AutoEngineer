# Dispatch and implementation audit

## Scope

Reviewed the nine exposed implementations, their queued and direct RCON paths, argument handling, lease ownership, cancellation, and startup behavior. The legacy public tool-method inventory is in `UPSTREAM_TOOL_INVENTORY.json` (116 excluded methods). That inventory is not a claim that every disabled legacy implementation has received a full security audit. The restricted build compiles only `AutoEngineerTools` and `SafetyTools` from the Tools folder and registers those two classes explicitly. It registers no MCP resources and does not initialize a chat listener.

| Exposed tool | Implementation and checks | Game effect |
|---|---|---|
| `autoengineer_policy` | Fixed policy v2, max walk 5; no model-supplied policy | None |
| `get_player_position` | Queued fixed Lua through PathfindingService; no arbitrary arguments | Read position |
| `get_nearby_entities` | Queued fixed Lua; finite radius greater than zero, at most 8; no remote center | Read entities |
| `scan_resources` | Queued fixed Lua; finite radius greater than zero, at most 50; no remote center | Read resource summary |
| `walk_to_position` | Queued; finite coordinates, tolerance (0, .75], timeout (0, 20]; valid owning lease; distance [.5, 5] checked after the queue wait | Normal walking, path visualization |
| `autoengineer_arm` | Direct safety Lua; GUID owner, exactly one connected character; reject other active owner | Clear old walking/mining; install guarded tick handler and lease |
| `autoengineer_renew` | Direct safety Lua; same owner, active and unexpired; cannot revive stopped lease | Renew 120 advancing-tick lease |
| `autoengineer_status` | Direct read outside gameplay queue; same active owner and single character | Read position, walking, tick |
| `autoengineer_stop` | Direct safety Lua; owning lease; later-tick acknowledgement | Latch stop; clear walking/mining |

The request filter rejects every unlisted tool name and unexpected argument key before invoking a handler. No raw Lua, console commands, teleportation, item spawning, building, crafting, mining dispatch, filesystem access, image processing, remote scan centers, or dynamic assembly registration is exposed. Safety operations intentionally bypass the gameplay queue so stopping cannot wait behind walking.

## Host boundary

The controller refuses a backend whose exact tool set or fixed policy handshake differs. All calls pass a closed host dispatch table. A walk requires a one-use approval permit bound to the exact arguments; changing arguments, reusing a permit or cancellation after approval denies dispatch. The model receives offered waypoint IDs, not tool names, arbitrary arguments or lease owners. The original five-tile validator and fresh-position check still run before approval is dispatched, and the backend repeats movement bounds independently.

The independent watchdog polls the direct status tool every .3 seconds. No .05-tile progress for five seconds, a 25-second observation budget, inactive status or invalid/lost telemetry ends the entire session. The enclosing SafetySession then requests a game-side stop; it does not silently retry uncertain watchdog failures. Known completed `no_path`, `stuck` and `timeout` outcomes can recover only after a stationary check and new approval. Near-duplicate failed endpoints are excluded; repeated approved moves from the same origin are independently denied. Recovery remains limited to three cycles.

## Configuration, credentials and events

Only loopback RCON and model endpoints are accepted. The RCON password has no Python or backend default and is passed through the environment, never local JSON. Backend child environment variables are allowlisted; cloud keys, parent model settings and custom config paths are not forwarded. Backend runtime state and per-session JSONL events live in ignored `.local/` folders. The MCP SDK may also supply its standard operating-system environment variables.

Events have a schema number, timestamp, session ID, fixed event type, approved boolean, cycle number and finite movement metrics. Failure status strings come from a fixed enumeration. Credentials, paths, raw tool arguments, prompts, model reasons, observations and arbitrary exception text are excluded. Audit-storage errors cannot interrupt emergency stopping.

## Limits

RCON remains a privileged administrative channel. This boundary constrains this MCP service and the normal dashboard/controller approval flow; it is not an operating-system sandbox, a cryptographic proof of human approval, or protection against another authorized raw-RCON client or arbitrary trusted local code. Exactly one player is supported. Tick-handler replacement by other code and paused simulation affect game-side protection. The legacy experiments are excluded from the source package; do not treat them as approved production entry points.
