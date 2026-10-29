# The remaining AI Helper workspaces - implementation plan

**Status: a plan, not an implementation.** Nothing in this document has
been built. The AI Helper stays **read-only** throughout: no gameplay
command, no placement, no blueprint in the game. The autonomous gameplay
functionality is **not** started and stays locked.

## The rules every workspace inherits

These are not per-workspace choices. They are the project's.

| rule | how it is kept |
| --- | --- |
| **read-only** | a widget never holds a transport, a session or a command string. The shell and the widgets import **no** `rcon`, `subprocess`, `socket`, `requests`, `http` or `urllib` module. `tests/test_qt_telemetry_integration.py` asserts this with an `ast` check on the real imports. |
| **no fabricated data** | every value comes from a validated model. A field that was not observed is **absent**, not zero. The model layer is where that rule lives, so the widgets inherit it. |
| **no second engine** | a workspace **reuses** the existing service. It never re-implements the mathematics. |
| **bounded** | a workspace holds at most a configured number of rows, samples or pages. The bound is a constant in the module, not a runtime accident. |
| **not blocking** | the observation is polled on a **worker thread** and handed to the UI thread through the shell's `frameArrived` signal. No widget ever waits for the game. |
| **honest resets** | a telemetry reset or a long gap clears the history rather than drawing a line across it. |

## The services that already exist

Every workspace below is a **view** over these. None of them needs a new
engine.

| service | what it already does |
| --- | --- |
| `observation_coordinator` | the four observation kinds: `STATUS`, `TELEMETRY`, `MAP`, `CATALOG`. It owns the dedupe, the cache, the budget and the backoff. |
| `qt_observation_bridge` | turns a coordinator observation into a validated `UiFrame`. It orders the frames, coalesces the repeats and refuses the out-of-order ones. |
| `qt_telemetry` / `production_telemetry` | validates the telemetry payload and builds the rows. The bounds live here. |
| `qt_telemetry_history` | the bounded history behind the charts. |
| `catalog_assembly` | assembles the recipe and research catalog from the observed pages. |
| `recipe_material_planner` / `recipe_feasibility` / `effective_yield` | the R06 recipe maths: what a recipe needs, whether it is reachable, what it really yields. |
| `production_solver` | the R06 production planning. |
| `read_only_planning` | the read-only planning surface and its mechanics ledger. |
| `dashboard_inventory` | the inventory grid: the slots, the quality colours, the layout fingerprint and the changed slots. |
| `blueprint_document` / `blueprint_codec` / `blueprint_encoder` | the R07 blueprint codec: classify, decode, describe and re-encode with fidelity. |

## The four observation kinds and what the UI may poll

The coordinator's kinds are the **only** thing the UI may ask for, and
the bridge already enforces the rule that the recipe catalog is **not**
polled during a telemetry refresh.

| kind | tool | polled when |
| --- | --- | --- |
| `STATUS` | `autoengineer_view` with `noCatalog` | every refresh |
| `TELEMETRY` | `autoengineer_telemetry` | every refresh |
| `MAP` | `autoengineer_view` with the map arguments | when the map workspace is visible |
| `CATALOG` | `autoengineer_view` with `catalogPageSize` | **on demand only**, when the user opens the catalog |

## The six workspaces

### 1. Recipes & Research

**What it shows.** The recipe and research catalog: what a factory can
make, what it can research, and which of those are reachable right now.

**What it reuses.** `catalog_assembly` builds the catalog from the
observed pages; `recipe_feasibility` decides whether a recipe is
reachable; `effective_yield` gives the real yield rather than the
nominal one. The catalog is **paged** and requested on demand, so the
cost is paid only when the user asks for it.

**The layout.** A searchable table of recipes, a detail pane for the
selected recipe, and the research tree beside it. The catalog is
filtered **client-side** over the pages that are already loaded.

**The truthfulness rules.** A recipe that is present but whose
ingredients are missing shows as **unreachable**, not as absent: the
recipe exists, the factory cannot make it yet. A recipe that was never
observed is simply not in the table. The page indicator says how much
of the catalog is loaded, because a partially loaded catalog must not
look like a complete one.

**The bound.** The table holds at most `MAX_ROWS` rows; the loaded
catalog holds at most `MAX_CATALOG_PAGES` pages. The rest is reachable
by paging, never by loading everything.

**The risk.** A full Pyanodons catalog is large. The page size and the
row bound have to be small enough that the table stays responsive, and
the **filter** has to run over the loaded pages only.

### 2. Inventory

**What it shows.** The player's own inventory: every slot, what is in
it, and the quality of each item.

**What it reuses.** `dashboard_inventory` already builds the whole
grid: the real slot numbers, the positions, the provenance, the quality
colours, the tooltip text and the layout fingerprint. The workspace is
a **renderer**, not a model.

**The layout.** The Factorio-style slot grid, drawn with the cached
scene objects. Only the slots whose content actually changed are
repainted, which is what `changed_slots` is for.

**The truthfulness rules.** A slot that was not observed is **empty**,
never "unknown item". The quality of an item is shown only when the
observer reported it; an unreported quality is the normal quality, and
the tooltip says so rather than inventing a tier.

**The bound.** The grid is bounded by the inventory size the observer
reports, which is itself bounded. The workspace adds a row bound for the
*table* view, but the grid is a fixed size.

**The risk.** The inventory changes on every player action, so the
refresh rate has to be bounded by the coordinator, not by the widget.

### 3. Logistics

**What it shows.** The flows between the containers: what is in a
request, what is in a provider, and what is missing.

**What it reuses.** The logistics observation from the mod
(`observation_inventory.lua` and the view composer), the coordinator's
`MAP`-kind request, and the same validation and freshness model the
other workspaces use.

**The layout.** A table of the flows, with the direction and the item
count, and a detail pane for one flow.

**The truthfulness rules.** A flow that was not observed is absent. A
provider with **zero** items is shown as empty, and that is different
from a provider that was not observed. The distinction is the whole
point of the workspace, so the table keeps a per-row source.

**The bound.** The flows are bounded by the container count the observer
reports. The table adds `MAX_ROWS` on top.

**The risk.** The logistics view is the easiest one to make **slow**,
because it is tempting to poll it on every tick. It must be polled on
the same schedule as the telemetry, and never more often.

### 4. Production planning

**What it shows.** A plan: what to build and in what order, given the
observed factory and the observed catalog.

**What it reuses.** `production_solver` does the planning;
`recipe_material_planner` and `effective_yield` do the maths;
`read_only_planning` is the surface that reports the plan's status and
its mechanics ledger. The workspace shows a **result**, it does not
solve anything itself.

**The layout.** The plan's steps as a list, the missing ingredients
beside it, and the mechanics ledger the R06 service already produces.

**The truthfulness rules.** A plan is a **plan**, not an observation.
It says what *would* satisfy the goal, and it says so. It is never
presented as a fact about the running factory. A plan computed from a
**partial** catalog says that the catalog was partial.

**The bound.** The plan is bounded by the solver's own limits. The
workspace holds at most `MAX_ROWS` steps.

**The risk.** The solver is expensive. It must run **on demand** and on
a **worker thread**, never on the UI thread and never on every tick.

### 5. Blueprint Studio

**What it shows.** A blueprint: decode it, inspect it, and re-encode it
with fidelity.

**What it reuses.** `blueprint_document` classifies, validates and
describes; `blueprint_codec` decodes; `blueprint_encoder` re-encodes;
`blueprint_property_fixtures` provides the fidelity tests. The R07
codec is already proven by its own test suite.

**The layout.** The blueprint's contents as a **preview**, plus the
import and export controls.

**The truthfulness rules.** A blueprint that fails to decode is
reported as failed, with the reason. It is never partially shown. The
re-encoded blueprint is compared against the original and the result is
reported; a codec that loses a property says so.

**The bound.** The blueprint size is bounded by the codec's own limits,
and the preview draws at most `MAX_PREVIEW_ENTITIES` entities.

**The risk - and the hard rule.** The AI Helper **may not place a
blueprint in the game**. The Studio may show, decode, encode and
**export** a blueprint as a string or a file. It may **not** send it to
Factorio. This is the R07 pre-readiness boundary and it stays exactly
where it is until the narrow R04-R06 gate is verified.

### 6. Diagnostics

**What it shows.** The health of the observation path itself: what was
observed, how fresh it is, what failed and why.

**What it reuses.** The bridge's counters, the coordinator's counters,
the `Observation` truthfulness model, and the shell's freshness badge.

**The layout.** A table of the observation kinds with their last value,
their age and their state; a panel of the bridge's and the
coordinator's counters; and a panel of the recent errors.

**The truthfulness rules.** This workspace is the one that shows the
**errors**, so it must be the most honest of them all. A failed
observation shows the failure. A value that aged out shows as stale.
A kind that was never observed shows as not observed. Nothing is
smoothed over.

**The bound.** The error list is bounded, and the table is bounded by
`MAX_ROWS`.

**The risk.** The diagnostics workspace must never become the place
where a *fix* happens. It reports; it does not repair.

## The order of the work

Each workspace is a separate, independently verifiable chunk. The order
follows the **risk**: the cheap, read-only ones first, the expensive and
the gated ones last.

| # | workspace | why here |
| --- | --- | --- |
| 1 | **Diagnostics** | it is the cheapest, and it makes every later workspace observable |
| 2 | **Inventory** | the model already exists; it is a renderer |
| 3 | **Recipes & Research** | the catalog is paged and on demand; the risk is the size, not the logic |
| 4 | **Logistics** | the same model as the other table workspaces |
| 5 | **Production planning** | the solver is expensive and must stay off the UI thread |
| 6 | **Blueprint Studio** | the **last** one, because of the R07 pre-readiness gate |

## What each workspace must prove before it counts as done

The same four questions for every one of them:

1. **Does it show real data?** A live observation reaches it and the
   value is the observed one.
2. **Does it stay honest?** A missing observation shows as missing, not
   as zero, and not as a stale value.
3. **Does it stay bounded?** The row, page and sample bounds hold under
   a full Pyanodons catalog.
4. **Does it stay responsive?** The UI thread is never blocked, and the
   game's UPS does not move.

## The gates that are not mine to open

* the **live** acceptance needs the human's explicit authorization;
* the **R07** read-only work needs the narrow R04-R06 pre-readiness
  checkpoint to be verified;
* the **expanded Semi-Autonomous** work needs the Gate H1 signoff;
* the **Full Autonomy** stays locked, and the **five-tile** movement
  limit and the **emergency stop** stay exactly where they are;
* the **launcher default** may only be switched after the parity result
  is measured, and the switch itself needs the human's approval.
