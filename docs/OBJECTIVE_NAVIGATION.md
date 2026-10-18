# Objective navigation and path validation

In the dashboard, enter a resource name such as `iron-ore` or coordinates such as
`12,-8` in the Objective field before starting. Leave it blank for exploration.
Editing the field during a session affects only the next session. Console users
can set `$env:AUTOENGINEER_OBJECTIVE = 'iron-ore'` before launching instead.

Resource objectives use the nearest matching resource center in the initial
50-tile observation. That center remains fixed for the session, even if later
scans differ. An unobserved resource ends the session without movement. Coordinates
must be finite and within one million tiles of the map origin. Objectives are
session settings, not automatically persisted goals. Re-enter the same objective
on another session to continue. The persistent exploration map remains separately
selected by AUTOENGINEER_WORLD.

The controller offers a step of at most four tiles toward the objective plus
short compass detours. Qwen selects an offered ID; it cannot supply a distant
destination or change the objective. Remaining distance is shown with each offer
and result. Remembered failed endpoints and user rejections are still excluded.
Detours may temporarily increase objective distance. Every move requires approval;
each session still has at most three proposals. A verified position within .75
tiles of a coordinate, or two tiles of a resource center, completes the objective
and stops further proposals. This is an approach objective, not mining or crafting.

Rebuild the backend from the updated combined safety patch on its pinned upstream
revision. Apply it once to a clean checkout; do not layer it over older patches.
Policy v5 is required: an older backend is refused before the safety lease arms.
No new tool or arbitrary Lua interface is exposed.

After approval, Factorio computes a collision-aware path. Before setting any walking
direction, the backend rejects empty or oversized routes, nonfinite waypoints,
wrong endpoints, route length above five tiles, waypoints beyond five tiles from
the start, and player drift above .5 tiles while the path was being calculated.
The existing independent five-tile target-distance checks remain in Python and
the backend. A rejected path ends the session through the normal stop cleanup.
The five-tile path-length check can conservatively reject a short destination
requiring a longer detour. It bounds the planned polyline, not the exact distance
the player travels while following it. Dynamic collisions, latency and control
overshoot remain possible; final-position verification, watchdog and emergency
stop still apply. Validation happens after approval and before walking, not as a
guarantee shown before approval.

Offline checks:

```powershell
python -m unittest discover -s tests -q
dotnet run --project tests/backend-navigation/NavigationTests.csproj -c Release
```

The backend checks use the same pure validator source as the combined patch.
