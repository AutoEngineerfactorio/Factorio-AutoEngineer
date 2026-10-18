# Live 2D map and inventory

Start a supervised session in the dashboard. The Live map and inventory tab shows
the current player, observed resource centers, recent visited positions, failed
targets, selected objective and proposed waypoint. The activity log is in a
separate tab. Zoom changes only the display radius (24, 60 or 120 tiles); the map
has no game-action click handler. Human approval remains on the existing buttons.

Position and main inventory are read about once a second while the session is
active, including while waiting for approval or for the model. The inventory
shows item, quality and count. It excludes cursor, equipment grids and non-main
inventories. The read is capped at 2000 slots and 64 item/quality groups; partial
results are labeled. Empty inventory and unavailable inventory are distinct.

The map is a schematic of observed markers, not a terrain renderer or collision
map. Resource markers are aggregate centers, with their observation age shown
separately from live telemetry age. Up to 16 resource types, 64 visited samples
and 64 failed targets are displayed. Offscreen markers are clipped. Coordinates
increase east/right and south/down; the grid is ten tiles. Colors have a legend.

Data older than three seconds or a failed read is marked stale; the previous
snapshot remains visible. Session exit labels it as the last snapshot and stops
polling. A surface change requests a safe session stop, avoiding mixing surfaces.
The existing world ID must still match save, surface and player for persistent
memory. Idle monitoring without an active supervised session is not implemented.

Rebuild the separately obtained backend from the updated combined safety patch
on its pinned upstream revision. The controller now requires policy v4 and the
exact ten-tool list, adding only autoengineer_view with no arguments. This direct,
fixed Lua read bypasses the gameplay queue but cannot write game state or accept
arbitrary Lua. Approval permits, path validation, five-tile target limits, safety
lease and movement watchdog remain independent of the display. Telemetry failures
do not authorize moves or delay game-side stop cleanup. Local display frames are
not added to the structured agent event log.
