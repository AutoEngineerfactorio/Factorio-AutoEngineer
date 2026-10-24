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
the Factorio 2.1.23 active target; older profile results are archived; source/offline compatibility
does not replace a clean backend build and live read-only check on each exact runtime.
The view tool uses bounded optional catalog-page arguments within the policy-v8
restricted tool boundary.
It reads the actual character position, surface and main inventory, including while the user is in remote view.
The game-style map uses the running game's tile map colors, a palette-indexed one-tile raster,
charted terrain with dimmed fog, continuous resource patches, visible nature/building/enemy layers, and player/objective/proposal markers.
Drag to pan, wheel or radius selector to zoom, and Follow player to recenter. Map gestures never move the player.

## Map layers

The map is painted in this order, so each layer reads like the in-game map:

1. **Charted terrain** - the game's own tile map colors. Unobserved space stays black.
2. **Resource patches** - observed ore deposits rasterized into occupied world tiles and merged into continuous filled patches. There is no per-deposit outline, so an ore field reads as one patch instead of a black-outlined checkerboard.
3. **Buildings and entities** - exact observed footprints, drawn as rectangles at the observed bounding box or observed width/height. An entity with no observed geometry is drawn as a symbol, never an invented footprint.
4. **Player marker and labels** - the character polygon, the player name and the coordinate readout.
5. **Overlays, goals and history** - pollution, electric networks, logistics, turrets, stations, map tags, the objective and proposed route, and the visited/failed history markers.

Patch colors are taken from the verified Factorio 2.1.23 base prototypes
(`data/base/prototypes/entity/resources.lua`, `map_color`): iron `#6a8694`,
copper `#cd6337`, stone `#b09c6d`, uranium `#00b300`. Coal is pure black in the
game, so it keeps the game's hue at a legible lightness (`#31353a`).

## Bounds and fidelity
- A 256-by-256 tile window is read around the character. Panning or zooming beyond it shows black; it does not request distant observations.
- Terrain is queried only in already charted chunks; entities only in currently visible chunks. No charting, chunk generation or revealing uncharted terrain.
- Charted terrain is current server terrain, dimmed outside live visibility; it is not an exact reconstruction of Factorio's historical chart texture cache.
- Resource patches contain exactly the tiles the observer reported. A deposit contributes the tiles of its observed bounding box, its observed width/height, or its single observed position. Nothing is inferred from the resource name, and no tile is invented.
- Entity limits are 2048 resources, 512 natural objects, 256 own-force buildings and 128 enemies. A partial indicator reports limits. Entity markers are simplified shapes, not game sprites.
- The inventory preserves the game's own slot numbers and grid positions for up to 200 main-inventory slots. Empty slots stay visible as recessed wells, slots are never reordered by item name, and the column count adapts to the panel width. Larger inventories show partial status; equipment, ammunition and trash are outside this view.
- The grid is drawn Factorio-style: recessed slot frames, the item count in the bottom-right corner with a dark shadow, and a quality-coloured slot border plus badge for non-normal quality. Hovering a slot reports its name, count, quality and slot number.
- Item icons load from the locally installed game PNGs, cropping the 1x frame of the horizontal mipmap strip (the common file is 120x64 pixels). Base game, Space Age, quality, elevated-rails, recycler and core packages are searched, followed by the enabled mods listed in the installation's own `mod-list.json`. Set `AUTOENGINEER_FACTORIO_DATA` and `AUTOENGINEER_FACTORIO_MODS` for a nonstandard install. Missing icons use text labels. No proprietary game assets are included in the repository.
- Icon paths are always built from a validated prototype name inside the installation's own icon directories; a name supplied by game telemetry is never used as a filesystem path.
- Only changed slots are redrawn on an update, so the grid does not flicker and the scroll position is preserved. A disconnected observer or an old reading marks the panel as `STALE` while the last known contents stay visible.
- Old backends show an aggregate inventory fallback, clearly labelled as not real slot positions, and unavailable terrain rather than fabricated data.
- This is a map-style display, not a pixel-identical copy of the in-game UI. The dispatch boundary, human approval, five-tile limit and emergency stopping remain intact.

See [validation](DASHBOARD_MAP_VALIDATION.md) for tested behavior and limits.

Operating modes are documented in [OPERATING_MODES.md](OPERATING_MODES.md). The current mode-aware backend must be rebuilt before Semi-Autonomous sessions run.

## Supported in-game commands

The Factorio 2.1.23 input helper provides two registered player commands:

- `/autoengineer-status` confirms that the input guard is available and reports its takeover generation. This is read-only and is **not** evidence that the AI backend is connected.
- `/autoengineer-takeover` requests human control and increments the takeover generation once. Use it only for an explicit player takeover request or a separately authorized disposable test; never automate or retry it.

For graphical testing, confirm the approved isolated test profile, open the console, and enter `/autoengineer-status` once. Read the response and verify the input guard is available. Do not repeat the command merely because the response is delayed. These registered commands do not use `/c` and do not require Lua confirmation.

The dashboard and restricted RCON backend remain the source for AI backend connection, AI Helper mode, human takeover request, and telemetry availability. Keep `autoengineer_view` and `autoengineer_policy` on the restricted backend: registered player commands do not replace bounded telemetry, catalog, policy, lease, or stop operations. The production and power tabs report their own available, partial, or unavailable telemetry state; the input guard status is a separate signal.
