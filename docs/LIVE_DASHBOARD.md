# Live map and player inventory

Opening the dashboard starts a separate read-only observer. No model or AI session is needed.
Starting/stopping the AI leaves observation running; closing the dashboard shuts down its observer and owned MCP process.
Unavailable/disconnected reads mark the last snapshot stale; the observer retries without approving actions or arming a safety lease.

Rebuild the current backend patch before use. The view tool keeps the same no-argument interface and policy-v5 restricted tool boundary.
It reads the actual character position, surface and main inventory, including while the user is in remote view.
The game-style map uses the running game's tile map colors, a palette-indexed one-tile raster,
charted terrain with dimmed fog, visible resource/nature/building/enemy layers, and player/objective/proposal markers.
Drag to pan, wheel or radius selector to zoom, and Follow player to recenter. Map gestures never move the player.

## Bounds and fidelity
- A 256-by-256 tile window is read around the character. Panning or zooming beyond it shows black; it does not request distant observations.
- Terrain is queried only in already charted chunks; entities only in currently visible chunks. No charting, chunk generation or revealing uncharted terrain.
- Charted terrain is current server terrain, dimmed outside live visibility; it is not an exact reconstruction of Factorio's historical chart texture cache.
- Entity limits are 2048 resources, 512 natural objects, 256 own-force buildings and 128 enemies. A partial indicator reports limits. Entity markers are simplified shapes, not game sprites.
- The inventory preserves slot indices, empty slots, counts and quality badges for up to 200 main-inventory slots. Larger inventories show partial status; equipment, ammunition and trash are outside this view.
- Item icons load from locally installed game PNGs, cropping the first square mip level. Set `AUTOENGINEER_FACTORIO_DATA` to the game's `data` folder for a nonstandard install. Missing icons use text labels. No proprietary game assets are included in the repository.
- Old backends show an aggregate inventory fallback and unavailable terrain rather than fabricated data.
- This is a map-style display, not a pixel-identical copy of the in-game UI. The dispatch boundary, human approval, five-tile limit and emergency stopping remain intact.

See [validation](DASHBOARD_MAP_VALIDATION.md) for tested behavior and limits.
