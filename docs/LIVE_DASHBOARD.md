# Live map and player inventory

Opening the dashboard starts a separate read-only observer. No model or AI session is needed.
Starting/stopping the AI leaves observation running; closing the dashboard shuts down its observer and owned MCP process.
Unavailable/disconnected reads mark the last snapshot stale; the observer retries without approving actions or arming a safety lease.

The **Recipes & Research** tab browses only same-tick recipe and research metadata received
from the game. It includes item/fluid inputs and products, recipe enabled/hidden state,
crafting category/time, researched technologies, and observed technology recipe-unlock
effects, plus profile, force, surface and tick.
Partial catalogs and unqualified/stale snapshots are identified; they never become plans.
Unlock effects are not proof that research prerequisites are met or that a disabled recipe
is currently buildable. A selected item or fluid output can be expanded into bounded
material requirements using currently enabled, non-hidden recipes. The preview exposes
recipe batches, unresolved or ambiguous inputs, cycles, and uncredited co-products.
It is material accounting only: no machine counts, throughput, power, transport,
buffer, or buildability is inferred, and co-products do not offset other inputs.
The tab reports mechanics-ledger evidence counts without treating observation as
verification. Older backends explicitly show unlock effects as unavailable.
The **Production & Power** tab plots bounded force/surface item and fluid flow
statistics in units per minute. It selects at most four item and two fluid series
from a rotating deterministic bucket of 128 item and 64 fluid prototypes, showing
60 samples at two-second intervals (a two-minute window). Coverage is explicitly
partial when the prototype catalog exceeds the current bucket. These are not
machine-level measurements.

Power samples cover up to eight visible own-force electric networks discovered from
at most 128 poles in the local observation window. The adapter reports raw
joules-per-tick; the dashboard converts this to watts using Factorio's 60 ticks per
second. Its graph is a locally accumulated two-minute history of maximum production
and consumption, not an archived in-game history. Missing samples, partial coverage
and a non-advancing game tick are labelled. Bottleneck text is limited to observed
flow imbalances and low consumption satisfaction; candidates are prompts to inspect,
not diagnoses or proof of shortage. No selection or telemetry operation writes to
the game.

The adapter does not report machine compatibility or general production feasibility.
Source-level UI and offline tests do not claim Windows visual or live-backend
acceptance; rebuild and verify the read-only adapter against each exact runtime first.

Rebuild the current backend patch before use. The bounded view tool is designed for
the Factorio 2.1.22 primary target and 2.0.77 backport; source/offline compatibility
does not replace a clean backend build and live read-only check on each exact runtime.
The view tool uses bounded optional catalog-page arguments within the policy-v8
restricted tool boundary.
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

Operating modes are documented in [OPERATING_MODES.md](OPERATING_MODES.md). The current mode-aware backend must be rebuilt before Semi-Autonomous sessions run.
