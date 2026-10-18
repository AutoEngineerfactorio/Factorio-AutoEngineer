# Dashboard map and inventory validation — 2026-10-18

- 110 offline tests pass, including read-only observer dispatch rejection, idle polling, raster palette/index bounds, exact projected colors, unknown black pixels, slot identity, quality and retained emergency-stop regressions.
- Separate patched .NET backend builds successfully. NU1900 reported unavailable NuGet vulnerability metadata; dependency versions were not changed in this work.
- Same dedicated disposable save used throughout. No main saves loaded or modified; no license changes or game assets packaged.
- Actual GUI: idle AI with advancing live ticks and inventory; corrected square icons and ten-column slots; character position and main inventory remain valid in Factorio remote view; map pan/zoom, including zoomed-out one-tile raster, visually checked.
- Original coarse four-tile terrain and icon-strip rendering were corrected before release.
- Dashboard Stop acknowledged in the disposable world. Active mining cancellation under the final continuous map observer also passed: mining false, crafting queue empty, game-side stop acknowledged, zero displacement. Temporary slow-mining fixture restored.
- The controller/dispatch/safety lease and five-tile validator are unchanged. Full-detail observation and AI operate through separate owned MCP processes; the observer can call only the no-argument view tool.
- Terrain, ore patches, water and natural objects were observed. Non-normal quality, live enemy/combat rendering and large factories were not exercised in this save; quality and bounds have offline coverage. This does not claim a pixel-identical Factorio map, full inventory interaction, full surface coverage or complete Phase 3 gameplay.

See [display bounds and setup](LIVE_DASHBOARD.md).
