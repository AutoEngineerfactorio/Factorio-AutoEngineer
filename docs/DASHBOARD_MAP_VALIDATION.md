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

## Resource-patch map layer — 2026-10-25

The per-resource-entity rendering was replaced with a resource-patch layer so the
map reads like the Factorio in-game map instead of a black-outlined checkerboard
of individual ore deposits.

- Observed resource entities are rasterized into occupied world tiles and merged
  into continuous filled rectangles with **no per-deposit border**.
- Adjacent deposits of the same resource merge into one patch; different
  resources keep separate patches.
- Patch colors are the verified Factorio 2.1.23 `map_color` values from
  `data/base/prototypes/entity/resources.lua`: iron `#6a8694`, copper `#cd6337`,
  stone `#b09c6d`, uranium `#00b300`. Coal is pure black in the game and keeps
  the game's hue at a legible lightness (`#31353a`).
- Buildings keep their exact observed footprints (observed bounding box, or
  observed width/height). An entity with no observed geometry stays a symbol;
  nothing is inferred from the prototype name.
- Render order: charted terrain, resource patches, buildings/entities, player
  marker and labels, overlays/goals/history. Unobserved space stays black.

### Evidence

OFFLINE only.

- Focused map suite: **52 tests OK** across
  `tests/test_dashboard_map_layers.py` (19),
  `tests/test_dashboard_map_view_layers.py` (6),
  `tests/test_dashboard_map_render_order.py` (9),
  `tests/test_dashboard_map_properties.py` (3) and the pre-existing
  `tests/test_dashboard_map.py` / `tests/test_dashboard_map_projection.py` (15).
- Full offline suite: **816 tests OK** (exit 0).
- Ruff: `All checks passed!` (exit 0).
- `git diff --check`: exit 0.
- `python -B memory/code_quality_gate.py --stage quick`: **PASS**.
- `python -B memory/code_quality_gate.py --stage full`: **BLOCKED** — the pinned
  `.venv` interpreter is absent (unchanged pre-existing condition; no dependency
  was installed).
- A seeded sweep (`SEED = 20261024`, 300 randomized tile sets) proved that the
  merged patch rectangles cover **exactly** the observed tiles: 0 mismatches, so
  no tile is invented and no observed tile is dropped.

### Not claimed

This work is **not** verified against the live 2.1.23 dashboard. No Factorio
process was launched, no save was created or modified, no RCON command was sent
and no gameplay action was performed. The visual acceptance against the running
dashboard is still open.

## Nature map layer — 2026-10-26 (R08)

The generic nature circle was replaced by a dedicated nature layer that uses
Factorio's own map data and conventions.

- New module `agent/dashboard_nature_layers.py` converts the *observed*
  natural entities into drawable shapes. Trees, rocks and cliffs are
  distinguished by the observed prototype type, so a stone ore deposit is never
  confused with a mineable rock.
- Colours are the game's own. The observed prototype chart colour wins in
  Factorio's documented order (`friendly_map_color`, `enemy_map_color`,
  `map_color`); otherwise a verified Factorio 2.1.23 prototype colour is used.
  An observed colour that equals the runtime's white "no chart colour" value
  is rejected rather than painted.
- Trees use the verified 2.1.23 tint palettes from
  `data/base/prototypes/entity/trees.lua`, selected by the observed
  `graphics_variation` (the index wraps around the palette exactly as the game
  does), and shaded by the game's map shading factor 0.6667.
- Geometry comes only from the observed bounding box or the observed width and
  height. Nothing is inferred from an entity name.
- Natural objects are drawn as filled shapes with **no black selection-box
  outline**, in the render order between the resource patches and the
  buildings. An object with no authoritative colour is drawn as an outline-only
  marker, so its position stays truthful.
- The classified shapes are cached per observation, so panning and zooming do
  not re-classify a large forest; a new observation invalidates the cache.

### Live read-only evidence

Verified against the already-running isolated 2.1.23 instance that owns the
single persistent test save, using only `autoengineer_policy` and
`autoengineer_view`:

- 12 tools, `tools_match_policy_v8 = true`, policy version 8, max_walk 5.
- 30 nature entities observed with prototype type, entity type, direction,
  exact bounds and graphics variation; 22 resolved to a verified Factorio
  tint, 8 had no verified palette, **0 painted white**.
- The save's SHA-256 was identical before and after; no gameplay command was
  issued and no world state was changed.

### Not claimed

The exact minimap tree pixel is **not** reproduced: Factorio anti-aliases and
dithers the map tree mark against the terrain and no supported API exposes the
map blend factor. The dashboard uses the verified game map shading constant.
`medium-rock` and `small-rock` are `optimized-decorative` in 2.1.23 and are
not observable at all, so they are not drawn. The comparison against the
Factorio window is a colour and layout reference, not a pixel-for-pixel
target.

## Multi-chunk map observation — R08-C

R08-C completes the observation and rendering pipeline so the dashboard map
reproduces the Factorio in-game map over **many** aligned chunks instead of a
single window around the player.

### Confirmed root causes (R08-B)

1. **Terrain and entity windows did not match.** The backend read a
   **256x256** tile terrain raster but queried entities for only the
   **64x64** chunk containing the player. The map therefore showed terrain
   for sixteen times the area it showed natural objects for, which reads as
   "missing forest". The R08-B chunk grid was aligned; the *windows* were
   not.
2. **Only the player's chunk could be observed.** `autoengineer_view` had no
   way to select a chunk, so panning and zooming could not fetch anything.
3. **No multi-chunk cache.** Every frame replaced the whole map, so a region
   that had already been observed could not be revisited without a new read.

### What changed

- The observed window is now exactly one aligned **64x64** chunk: the terrain
  raster and every entity query cover the same 64 tiles.
- `autoengineer_view` accepts optional `mapChunkX` / `mapChunkY` chunk
  indices. They must be given together and each must be a bounded integer.
  The tool count and the policy-v8 boundary are **unchanged**; only two
  read-only arguments were added to an existing tool.
- New modules: `agent/dashboard_chunk_grid.py` (grid geometry and viewport
  chunk selection), `agent/dashboard_chunk_cache.py` (bounded, surface-scoped
  cache), `agent/dashboard_chunk_map.py` (chunk record model and merging).
- The dashboard sends a viewport request to the observer over the existing
  control channel. The observer turns it into a bounded list of chunk
  indices, observes only the chunks that are missing, stale or partial, and
  **supersedes** an obsolete request instead of queueing it.

### Cache architecture and invalidation rules

- Keyed by `(surface, chunk_x, chunk_y)` on the 64-tile aligned grid.
- Terrain, resource entities, nature entities, buildings, enemies and
  overlays are stored separately per chunk.
- Each chunk records its surface, chunk indices, tick, observation time,
  `partial` flag and `chunk_complete` flag.
- Status is `fresh`, `stale` or `partial`. **`partial` outranks `stale`**: a
  chunk that could not be fully observed is never promoted to complete.
- A surface change clears the cache entirely, so a chunk observed on one
  surface can never be drawn on another.
- `reset()` clears every chunk and bumps a generation counter, for a game
  restart. A mod-set change invalidates the affected chunks through the
  normal staleness path.
- The cache is bounded by a configurable chunk count with LRU eviction, and
  by a per-chunk entity budget.
- Entities that two adjacent chunks both report are emitted once, so a shared
  chunk boundary cannot produce a duplicated tree.

### Live read-only evidence (Factorio 2.1.23)

Against the already-running 2.1.23 instance that owns the single persistent
test save, using only `autoengineer_policy` and `autoengineer_view`:

- **12 tools**, `tools_match_policy_v8 = true`, policy
  `{"version":8,"max_walk":5,"restricted":true,"mode":"helper"}`.
- **Five adjacent chunks** observed with exactly aligned origins:
  `-2 -> (-128,0)`, `-1 -> (-64,0)`, `0 -> (0,0)`, `1 -> (64,0)`,
  `2 -> (128,0)`. Every chunk reported a 64-row x 128-hex raster, that is
  exactly 64x64 tiles, matching its entity window.
- **0 boundary duplicates** and **0 entities outside their own chunk**.
- **Invalid chunk requests rejected**: x-only, y-only, out-of-range positive
  and out-of-range negative.
- **Repeated identical observations** returned identical rasters and
  identical entity lists.
- **The player did not move** (0,0 -> 0,0) and **the save digest was
  identical** before and after.
- Chunk read latency 137-179 ms (mean 157 ms).

Evidence: `.local/live-pillow-2.1.23/evidence/r08c-chunk-live.json`.

### Dense-forest observation results

In the live chunk `0,0` (64x64 tiles) the observer reported **497 entities**:

| Prototype | Count |
|---|---|
| `stone` | 244 |
| `iron-ore` | 119 |
| `tree-02-red` | 115 |
| `dead-grey-trunk` | 12 |
| `big-rock` | 3 |

Across the three observed chunks: **353 natural entities** (211 `tree-02-red`,
83 `tree-08`, 38 `dead-grey-trunk`, 21 rocks and dead trees) and **728
resource entities**. That is a dense forest by Factorio's own density, and
every one of those entities was inside the same 64x64 window as its terrain.
This is the direct answer to the R08-B "missing forest" report: the forest was
never missing, it was being drawn at one sixteenth of the area it covered.

Every observed entity reported a bounding box, a chart colour, a prototype
type and a graphics variation, so the nature layer could use the verified
tree tint palettes and the verified resource prototype colours.

### Performance measurements

Offline, from `tests/benchmark_dashboard_chunks.py`
(`tests/benchmark_dashboard_chunks.json`):

| Scenario | Observe (mean) | Merge (mean) | Notes |
|---|---|---|---|
| Dense forest, 1200 entities | 1.35 ms | 1.13 ms | one chunk |
| Dense region, 2400 entities, 4 chunks | 2.46 ms | 1.87 ms | 4 chunks |
| Four adjacent chunks | - | 0.33 ms | 400 entities |
| Wide viewport, 64 chunks | 0.38 ms | 0.13 ms | cache 758 KB |
| Zoom/pan request encode | 0.16 ms | - | 40 requests |
| Zoom/pan chunk selection | 0.11 ms | - | 40 viewports |
| Revisit the same viewport | - | - | **0.06 ms, hit rate 1.00** |
| Large prototype set, 2000 distinct | 2.37 ms | 2.02 ms | modded scale |
| Repeated identical observation | 0.27 ms | 0.17 ms | cache stays 68 KB |
| Memory bound | - | - | 8 chunk budget held at 8 chunks, 95 KB |
| Partial chunk reporting | - | - | 1 partial, merged map marked partial |

A slow backend response adds its latency in front of the cache cost; the
cache itself is unaffected. The revisit hit rate of 1.00 is the measurable
form of "returning to a previously viewed region costs no retransmission".

### Remaining API limitations (not defects)

These are properties of the supported Factorio 2.1.23 API, verified against
the offline archive with `agent/factorio_api_2123.py`:

1. **A resource patch's extent is not observable.** Factorio's map draws the
   whole ore field as one filled blob. In 2.1.23 `LuaEntity` has no patch
   area, extent or amount accessor, and there is **no `LuaResource` class**
   at all. The observed ore node's bounding box is only 0.195 x 0.195 tiles.
   The dashboard therefore draws each observed node on its own tile and
   merges contiguous tiles, which is truthful but produces a speckled field
   instead of a solid blob. Drawing a solid blob would require synthesising
   the field extent, which this work explicitly forbids.
2. **The runtime chart colour is always white.** `LuaEntityPrototype.map_color`
   returns `{255,255,255}` for every prototype in the running game, which is
   the game's "no chart colour" marker. The dashboard never paints white; it
   uses the verified 2.1.23 prototype colours and tree tint palettes instead.
3. **Tree marks are anti-aliased and dithered by the game.** No supported API
   exposes the map blend factor, so the exact tree pixel is not reproduced.
4. **`medium-rock` and `small-rock` are `optimized-decorative`** in 2.1.23 and
   are not observable as entities, so they are not drawn.

### Not claimed

This work does **not** claim pixel-identical parity with the Factorio map.
The terrain raster, the chunk geometry, the entity positions, the resource
colours and the tree tints are authoritative and were compared live. The
remaining differences are the four items above, which are API limits of the
supported 2.1.23 version and are documented rather than papered over.

The live screenshot comparison uses a north-up, tile-scale-normalised
rectangle for the dashboard image and the matching region of the captured
Factorio window. Images with different viewport extents are **not** accepted
as evidence of parity.

## R08-D final map completion — 2026-10-26

**Status: see the final report.** This pass fixes the four visual defects that
were still open after R08-C: the map was too small, the enemies were not
visible, the ore field read as scattered dots and a dense forest read as
scattered specks.

### A. Map-first layout

- The dashboard window opens at **1920x1080** (minimum 1280x800) instead of
  1600x960.
- The map tab takes the dominant share of the workspace pane (weight 9 against
  the mission-control column's 1).
- The map canvas asks for 980x660 instead of 660x310 and fills the pane it is
  given.
- The **default map radius is now 128 tiles** instead of 60. This is the single
  change that makes the observed world readable: at a 60-tile radius the
  viewport covered world x in [-35, 85], while the observed enemies live at
  x = 92..95, so a correctly observed enemy was simply off-screen.
- The inventory pane is narrower (300 px instead of 425 px) and stays behind
  the existing "Show inventory" control, so it remains available but does not
  compete with the map. The map-first default and the toggle are unchanged.

### B. Fog of war

The three Factorio 2.1.23 tile states are now one shared model in
`agent/dashboard_map_layers.py`, used by the renderer and checked against the
backend source:

| state | terrain | live entities |
| --- | --- | --- |
| `unexplored` | black | none reported |
| `charted` | darkened by the map shading factor 0.6667 | none reported |
| `visible` | full brightness | reported |

- The backend already implemented this exactly: an uncharted tile stays on
  palette index 0 (`#000000`), a charted-but-not-visible tile is written as
  `map_color * 0.6667`, and every entity is gated on `visible()`.
- The renderer previously used a local `* 2 // 3` expression for the legacy
  `tiles` path. It now calls the shared `shade_fog_color()` helper with the
  same factor, so the two paths cannot drift apart.
- `tests/test_dashboard_fog_state.py` pins the three states, the shading
  factor, the unusable-colour rejection and the backend/renderer agreement.

### C. Enemies

**The enemies were observed all along; they were off-screen.**

LIVE READ-ONLY observation of the running Factorio 2.1.23 recorded three
`small-biter` entities at world (92.57, 17.44), (93.22, 19.79) and
(95.30, 22.60), each with an observed bounding box, in chunk `1,0`.

- The observation path was correct: the backend's `find_entities_filtered`
  with `force="enemy"` returned them, and the `visible()` gate kept them
  truthful.
- The default 60-tile viewport put them outside the visible world rectangle.
  The 128-tile default radius now includes them.
- The backend now also records an enemy's `entity_type`, `prototype_type` and
  its **own** `enemy_map_color`, so the marker uses the colour Factorio charts
  that enemy with instead of a guessed generic red.
- The marker is drawn at 5..11 px with a light outline and a dark halo so it
  stays readable over a pale terrain tile or an ore patch.
- Enemies are still reported only for currently visible chunks, so nothing is
  leaked through fog.

### D. Ore patches

**Root cause, measured live:** an ore field is reported as many individual
ore nodes, and each node's own bounding box is only **0.195 x 0.195 tiles**.
The old code put each node on its own whole tile, so a field of 436
`copper-ore` nodes became 436 separate single-tile dots.

The observed field extents, from the live observation:

| resource | observed nodes | extent |
| --- | --- | --- |
| `copper-ore` | 436 | 24 x 25 tiles |
| `iron-ore` | 636 | 31 x 34 tiles |
| `stone` | 249 | 18 x 18 tiles |

The patch layer now:

1. groups the observed nodes into the **separate deposits** they form
   (8-connected, so a one-tile gap keeps two fields apart),
2. fills each deposit by adding a tile only when it is surrounded by observed
   ore on **three of its four sides**, which keeps the deposit's outer
   boundary exactly on the observed nodes, and
3. merges the filled tiles into continuous filled rectangles.

Replaying the live iron-ore density through the new code turns 738 scattered
tiles into **2 rectangles covering 1052 tiles** - one continuous patch, like the
in-game map. No tile outside the observed field is invented, and two deposits
separated by empty space stay separate.

### E. Forest

A tree's observed footprint is 0.797 x 0.797 tiles, so at the wide default
zoom one tree was about one pixel and a dense stand of 285 `tree-08` trees
read as scattered specks.

- The tree glyph now keeps a **minimum on-screen radius of 2.5 px**
  (`TREE_MIN_MARKER_PIXELS`). This is a display size only: it never adds a
  tree, never moves a tree and never changes an observed position. Adjacent
  observed trees overlap into forest cover.
- The colour stays the verified dark chart green `#31401b` that was measured
  from the live Factorio minimap.

### F. Decoratives - investigated, deliberately not implemented

`LuaSurface::find_decoratives_filtered` **exists** in Factorio 2.1.23 and the
LIVE READ-ONLY probe of the running game confirms it works: it returned 5
objects for a 16x16 tile area next to the player.

**But the returned objects cannot be placed on a map.** The probe read every
field of the returned objects:

```
DECOR_COUNT=5 | ITEM1 TYPE=table FIELDS=amount=1 | ITEM2 TYPE=table FIELDS=amount=1
DECOR_PROTO=NO_PROTOTYPE
```

Each object exposes **only `amount`**. There is no `position`, no `name`, no
`prototype` and no `valid` flag, and the 2.1.23 runtime API documents no
`LuaDecorative` class - only `LuaDecorativePrototype`. `DecorativePrototype`
has no `map_color` either.

A decorative therefore has neither a world position nor an identity in
Factorio 2.1.23. Drawing one would require inventing both, which this work
explicitly forbids, so **decorative support is not implemented**. The
limitation is documented here rather than papered over, and the
`medium-rock`/`small-rock` optimized decoratives remain unobservable for the
same reason.

Evidence: `.local/live-pillow-2.1.23/evidence/r08d-decorative-live.json`,
produced by `tests/live_r08d_decorative_probe.py` (a read-only `rcon.print`
of the returned object's fields).
