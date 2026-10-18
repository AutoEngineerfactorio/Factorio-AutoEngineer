# Live 2D dashboard map and inventory — local validation

Added a read-only observed map and main-inventory tab to the existing dashboard. Player position and inventory refresh about once a second during supervised sessions, including model/approval waits and movement. The map shows resource centers, recent visited and failed locations, objective and proposal markers, grid and display-only zoom. Inventory distinguishes item quality, partial and unavailable data. Stale/end-of-session snapshots are labeled; resource observation age is separate.

Validation:
- 90 Python tests passed, including frame validation, bounds, inventory/quality, axes, stale states, read-only dispatch, surface-change stop and old-backend rejection.
- Separate policy-v4 backend Release build: zero warnings/errors.
- Combined patch applied to clean pinned upstream and reproduced tested backend source.
- Actual Windows dashboard opened and inspected with the same dedicated test save; inventory and position matched independent game observation.
- Map visibly followed approved movement and displayed resource, visited and failed markers.
- A one-wood inventory fixture appeared live; removal appeared live too. Original inventory restored.
- Actual dashboard buttons: three manual test approvals, one rejection, three Stop acknowledgements over three sessions.
- Final active-motion test used a slower disposable-world speed: independently observed walking before pressing Stop; stopped before reaching target; zero drift over 183 advancing ticks. Original test speed restored.
- Existing five-tile validator AST unchanged; game-side lease, watchdog and route checks retained.

Only ten closed-dispatch tools are exposed. The added autoengineer_view accepts no arguments, uses fixed read-only Lua and bounds inventory to 2000 slots/64 item-quality groups. Policy v4 is required. The UI has no map click action. Display failures cannot grant movement approval or delay stop cleanup; a surface change stops the session.

Limits: schematic markers rather than terrain; at most 16 resource types, 64 visited and 64 failed samples displayed. Resource data is cached separately, and aggregate centers are not actual deposit outlines. Main inventory only; no cursor, armor/equipment grids or container inventories. No live polling while idle: last snapshot remains labeled. One selected save/surface/player ID is still required for exploration memory. Space Age inventory quality is supported structurally but Space Age gameplay has not been validated here.

These results were recorded before publication; the dashboard roadmap item is complete. No license changes or main saves touched.
