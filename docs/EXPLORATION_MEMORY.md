# Persistent exploration memory

Before launching the dashboard or supervised agent, choose a unique identifier for
the exact save, surface and player being used:

```powershell
$env:AUTOENGINEER_WORLD = 'my-save-nauvis-player1'
```

Keep this identifier across sessions of that world. Use a new identifier after
loading a different world, restoring an earlier save, changing surface/player, or
regenerating terrain. World identity is selected manually, not detected by the
backend. Without this setting, movement still works with session-only history.
An empty identifier or invalid map stops the session safely.

Maps are private JSON files under `.local/exploration/`, named by a hash of the
identifier. They contain only a version, observed positions and failed endpoints;
they are ignored by Git. Only one dashboard/agent should use a world identifier
at a time. Concurrent writers are not supported.

Observed starting and final positions mark two-tile cells as visited. These are
sampled cells, not a continuous trail or a claim that terrain is traversable.
Unvisited candidate endpoints are offered first and marked for the model; visited
areas remain available for detours. Failed verified movement endpoints exclude
new targets within one tile, including after restart. Rejections by the user
remain session-only; they do not label terrain as blocked. Failures are conservative
hints, not a pathfinding map: changed obstacles require a new world identifier to
start fresh. Each category retains its most recent 10,000 distinct entries.

Writes replace the file atomically. Invalid data and write failures end the
session through the existing safety cleanup rather than silently ignoring memory.
Connection loss and cancellation do not invent a failed endpoint without a
verified final observation. The existing approval gate, dispatch restrictions,
five-tile validation, movement watchdog and emergency stop remain in force.

See [live validation](EXPLORATION_VALIDATION.md) for restart, approval and Stop test results.
