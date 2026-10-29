# Approved AutoEngineer dashboard — implementation contract (2026-10-28)

## Product decision

Use the approved charcoal/industrial mockup as the visual and workflow target.
This is the **active Qt/PySide6 application** at
`D:\AI\Factorio-AutoEngineer-Source`, not the old Tkinter demo or the
outdated public GitHub checkout. Factorio target: **2.1.23 only**.

The mockup was conceptual: its save name, output rates, game version, task
progress, confidence, and completed work were example values, **not**
observations. No screen may copy those example numbers into live state.

## Visual design system

- Dark graphite/black background and restrained steel card panels.
- Orange selection highlight, orange primary actions, green truthful/healthy
  observations, amber warnings, red confirmed stop/danger, muted unavailable.
- Left sidebar: Dashboard, AI Helper, Blueprint Planner, Telemetry, Research,
  Inventory, Power, Map, Logistics, Logs & Diagnostics, Saves, Settings.
- Compact global header: branding, observed game/profile, live/snapshot/offline,
  active permission mode, data freshness.
- Dashboard cards: Quick Control, Current World, AI Session, Live Telemetry,
  Blueprint Planner, Production & Tasks.
- Responsive 1440p desktop first, scrollable on shorter resolutions; readable
  labels and hover help; native Windows font rendering required.

## Actual integration (first implemented increment)

- `agent/qt_control_center.py`: new dashboard Overview with navigation to
  existing Qt recipe planner, research queue, blueprints, map, inventory,
  telemetry, and electrical workspace.
- `agent/qt_shell.py`: installs that Overview, reorders/labels the nav rail,
  and forwards verified status/metric frames to the cards.
- `agent/qt_header.py`: compact header, retains metric API for tests.
- `agent/qt_theme.py`: graphite industrial card and button styling.
- `agent/qt_blueprint_workspace.py`: missing-observed-catalog diagnostic now
  explicitly asks for a complete authoritative catalog.
- `tests/test_qt_control_center.py`: navigation, missing data, disabled unsafe
  controls, observed state and disconnect tests.

All edits remain in local working tree. None claim to have enabled gameplay
controls, switched the default launcher, or finished backend functionality.

## Functional completion gates — execute in order

### Gate A — reliable read-only dashboard
- Single cached, bounded observation stream; no per-widget Factorio polling.
- Display actual save/profile/game version, UPS, map, inventory and uptime when
  observed. Unknown/partial/stale data must show its true state.
- Production: input/output items per second and minute, modded fluids and
  byproducts, research progress, logistics/bots/trains, and power networks.
- Historical sparklines from bounded history only, with units and time basis.
- Settings and diagnostics show real connection/worker errors and performance.
- Test offline, stale/disconnect/reconnect, live vanilla and pY, UI thread and
  Factorio UPS impact; target stable 60 UPS.

### Gate B — universal AI Helper
- Helmod-like editable production chain planner based on active mod mechanics.
- Observed technology/research gating, resource availability, inventory,
  bottlenecks, alternatives, modules, beacons, quality and power requirements.
- Recipe/technology cache persists by verified version + profile + mod
  fingerprint, with safe invalidation and paged refresh on demand.
- No hardcoded vanilla or pY designs; both are acceptance test profiles.

### Gate C — blueprint workshop
- View/edit/browse/search/import/export/organize local blueprints and nested
  books, with Factorio-style visual preview and reversible edits.
- Generate mathematically consistent layouts from R06 plans; verify entities,
  recipe/machine matching, connections, power, fluids, belts, inserters,
  rail/bot/circuit constraints and active researched recipes.
- Distinguish local draft, syntax-valid export, game-validated blueprint and
  *built in world*; never claim one implies the next.
- Stress test complex pY chains; preserve safety and game UPS.

### Gate D — operational controls
- Implement verified game/save/profile chooser for the two test profiles
  (vanilla, pY), mutually isolated configs/mods/saves.
- Launch/stop/restart/save only through an explicit supervised service and
  confirmation; buttons reflect actual process state and stop acknowledgments.
- AI Helper mode remains read-only. Semi-Autonomous requires per-action
  approval and functional human takeover. Full Autonomous stays locked
  until independent safety, recovery and long-running acceptance gates pass.
- Task queue shows actual verified objectives, progress, errors and journal
  checkpoints, not fabricated ETAs or confidence scores.
- Launcher switch to Qt only after functional parity and a tested rollback.

## Hard constraints

- Never run a live game or alter saves merely to render the UI.
- Never start 2 Factorio servers/AI model processes by accident.
- Never issue console Lua or bypass registered-mod-command restrictions.
- Reuse R09/R10 observation coordinator and caches; keep RCON off the UI thread.
- Only modify directly relevant files in the large dirty worktree; no reset,
  clean, bulk staging or GitHub push without explicit approval.
- Test against the current 2.1.23 API and both isolated profiles.
- Full code cleanup/consolidation comes **after** complete AI Helper acceptance.

## Acceptance evidence

Record exact test command, test count, lint status, screenshot, and any live
acceptance separately. A screenshot proves only layout; it does not prove that
buttons, game operations or telemetry work in a live session.

## Reference layout verification — latest increment

The real Qt shell now uses vector icons, explicit Windows font discovery,
orange branding and sidebar selection, industrial gradient card headers, a
compact quick-control row, world summary/preview placeholder, AI session,
six telemetry tiles, and blueprint/task tables. Header settings and diagnostic
buttons navigate to the existing workspaces. No notification feed is invented.
Power readings show units; missing network updates erase old telemetry, stale
readings are marked, and disconnect clears observations. Unsupported controls
are disabled with hover explanations. Queue tables stay empty until connected
verified queues exist. The world preview is explicitly unavailable until an
actual image source is integrated.

Verification: eight focused dashboard tests, twelve header tests, 73 shell
tests, full offline 2,441 tests OK / 92 skipped, clean Ruff/Pyright/VS Code
Problems. A native Windows window was inspected and Blueprint Planner opened
through the sidebar. The standalone shell was offline; that check did not start
Factorio or prove live telemetry. The user requests Pillow for subsequent
saved-image inspection and comparisons. No default-launcher migration or game
control acceptance is implied by this design increment.


## Functional verification after the reference-layout increment

The chain-planner tab, research/local-pollution telemetry, robot dashboard card,
correct delivered-power semantics and user-driven Factory Map observations are
now wired through shared read-only services. Stale/disconnected data cannot
remain labelled current. Catalog paging resumes after budget pauses instead of
stopping at an incomplete snapshot. Runtime version/player context is preserved.

The five-minute populated fresh-pY combined run passed at 59.89 average UPS with
zero dashboard/observer transport failures, 19 local-model responses and no fluid
stalls. Pillow inspected its real-data 1,920 x 1,080 dashboard capture. Fresh pY
planner/map/draft/disconnect UI acceptance also passed; actual terrain rasters
are now rendered, not only entity markers. The latest full gate has 2,503 tests
OK / 93 skipped, clean Ruff and 0 VS Code errors/warnings. Skipped optional Lua
coverage was complemented by 40 passing tests using the Lua-capable interpreter.

Remaining limitations still apply: current blueprint output is a machine-layout
draft, advanced production mechanics need qualified adapters/physical proof,
initial complete-catalog capture can severely lower the measured tick rate,
and native FPS/GPU measurements and default-launcher migration remain open.
No H1 acceptance or default UI switch is claimed by this increment.
