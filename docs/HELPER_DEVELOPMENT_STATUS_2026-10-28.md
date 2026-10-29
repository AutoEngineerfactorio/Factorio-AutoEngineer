# Helper development verification — October 28, 2026

Status: IN PROGRESS. Gate H1 is OPEN. Fully Autonomous remains locked.
This record distinguishes current verification from historical checkpoints.

## Repairs in this session

- Machine observation uses the bound `get_crafting_speed()` method and the
  declared `fluidbox_prototypes` / `volume` fields. The backend and mod catalog
  call the bound method without passing an extra receiver. Strict Lua tests pass.
- Catalog sweep collects exclusions from every page and records a balanced
  declared/emitted/excluded accounting result; interrupted sweeps fail that check.
- The active backend catalog path was found returning only summary rows. It now
  requests the registered rich capability envelope and preserves its catalog
  status, tick, fingerprint, research, machine and recipe metadata.
- The existing mod capability handler called a nonexistent module return. It now
  calls the function exported on `observation` and requests catalog-only reads.
- Blueprint generation refuses partial/truncated catalogs and unverified
  independent/shared probabilistic yields. This is a safety correction, not
  universal production-math or connected-layout acceptance.
- Dashboard type errors were corrected without disabling diagnostics. The
  refreshed VS Code Problems gate reached 0 errors / 0 warnings.

## Evidence and scope

- Initial project regression: 2,399 tests, 1 failure, 87 skipped. The failure was
  partial-catalog generation in Blueprint Studio.
- Intermediate project regression after scoped repairs: 2,406 tests, OK,
  89 skipped. The optional Lua engine is absent from this environment.
- Intermediate system-Python regression: 2,462 tests, OK, 229 skipped; Qt tests
  are unavailable there, while Lua tests run. These runs are complementary.
- Strict targeted Lua regressions for bound methods and registered catalog
  routing were run with the Lua-capable system interpreter and passed.
- Restricted backend source and synchronized patch apply/build checks passed
  with zero warnings/errors, including the rich-composer transport repair.
- Fresh vanilla R10-B inventory acceptance passed. Original source save SHA-256
  was unchanged and both owned game processes stopped.
- The first expanded Pyanodons catalog run FAILED: metadata and machine rates
  were absent from the summary transport. This prompted the integration repair;
  it is not accepted as a passing rich-catalog run.
- The approved creative fixture observed 8 populated logistic networks,
  320 logistic robots, 200 construction robots and 24 wagons. Cargo iron and
  wagon water were observed through registered read-only commands. Final
  five-minute stress PASSED: 59.92 average UPS, 1 sample below 58, 14 AI
  responses, 0 observer failures/timeouts, 0 fluid stalls, unchanged source save.

## Remaining acceptance work

1. Catalog snapshot architecture and the fresh Pyanodons UI integration now
   pass. The complete snapshot accounts for 9,467 supported recipes + 679
   named exclusions = 10,146 declared recipes, with all 648 machines and a
   non-null fingerprint. Remaining: live vanilla parity and the initial
   snapshot UPS dip; do not mark the overall performance/H1 gate passed.
2. Complete advanced production-flow mechanics and measured physical-factory
   predictions; representative fixtures do not establish universal coverage.
3. Complete connected blueprint routing/buildability and real-client fidelity.
   Current generators explicitly produce machine-layout drafts only.
4. Add spatial filtering; measure combined dashboard/model/observer performance,
   including rendered FPS/GPU where instrumentation exists.
5. Finish failure/recovery/security/endurance and the user-reviewed H1 record.
6. Capture a scoped local Git checkpoint after final review. Do not bulk-stage
   the large pre-existing dirty tree or publish private evidence/configuration.

## Fresh Pyanodons world — created and verified

- New save: `.local/launcher-profiles/2.1.23/data/saves/autoengineer-py-fresh-20261028.zip`.
- Generated normally with Factorio 2.1.23.87750 and the existing full pY mod set.
  The Milestones mod detected its Full Py Mods preset. No creative entities were
  added to this world; the creative stress fixture was a separate generated world.
- Fresh server and graphical client loaded a disposable copy. Machine/catalog
  reads succeeded; the new source save SHA-256 was unchanged after validation.
- Source SHA-256: `5f7da3d8d76572f2131fc4e4dff2c4d5756e4531c2be3a93c60dcaa288cd7dc4`.
- With explicit user approval, only launcher `save_path` was changed; its private
  configuration backup remains under `.local/live-pillow-2.1.23/world-generation-20261028`.
- Read-only environment and future stress tests now share the fresh pY default.
  Existing vanilla and old modded saves are retained and their hashes unchanged.
- Earlier full quality gate: PASS; 2,410 tests OK, 90 skipped, Ruff clean; refreshed
  VS Code diagnostics: 0 errors / 0 warnings. Pyright also passed.
- No game or model process remains running after validation.


## Latest catalog and dashboard verification

- Fresh pY full catalog sweep: 318 pages, one tick/fingerprint, 23.2 seconds.
  Actual Qt bridge integration: 80 pages in 10.094 seconds, mean UI apply
  27 ms, maximum 156 ms. Source save unchanged; owned test game processes
  stopped. The initial capture included a 9.6 UPS sample: performance remains
  open despite the completed snapshot and passing UI integration.
- UI estimate, machine-layout draft codec round trip, and disconnect planning
  invalidation passed. These do not prove routed or physically buildable designs.
- Latest full offline gate: 2,441 tests OK, 92 skipped, Ruff clean; VS Code
  Problems 0 errors / 0 warnings. Separate Pyright: 0 errors / 0 warnings.
  The final world-metric color-only adjustment passed its eight dashboard tests.
- The Qt Overview now follows the supplied industrial dashboard reference:
  orange branding/navigation, compact header, quick controls, paired world/AI
  cards, six telemetry tiles, blueprint queue and production task table.
  Unconnected queues and measurements remain explicitly unknown. Gameplay
  controls remain disabled without a verified controller. No launcher switch.
- Real Windows visual inspection and Blueprint Planner navigation succeeded.
  Offline saved-image rendering is separate evidence; future image inspection
  and comparisons should use Pillow, as requested by the user.
- Isolated optimizer dependencies installed: SciPy 1.18.0 and NumPy 2.5.4,
  pinned with wheel hashes; pip dependency check passed. Solver implementation,
  runtime machine-energy unit correction, full advanced-mechanics validation,
  physical layout validation and H1 human signoff remain outstanding.


## Verified repair increment — 2026-10-28, latest

This section supersedes earlier test counts and outstanding implementation
notes above. It does not declare all six delivery items or Gate H1 complete.

- Full offline gate: 2,503 tests OK, 93 skipped; Ruff clean; current VS Code
  Problems 0 errors / 0 warnings. Complementary Lua-capable run: 40 tests OK.
  The isolated environment passes pip check. Restricted backend patch/build
  verification completed with zero warnings/errors before these Python fixes.
- Runtime machine power is normalized from joules/tick to watts at the adapter
  boundary; observed electrical idle drain is retained. Dashboard delivered
  power is distinguished from available generation and requested consumption.
- Sparse integer production-flow optimization and a background Qt chain-planner
  tab now support base-yield alternatives, coproduct balances, explicitly bounded
  surplus, seeded cycles, shared machine-stock caps and power limits. Requests
  containing unobserved material identities are rejected. This remains an estimate.
- Positive tiny flows, integer activation, startup reachability, shared machine
  limits and malformed inputs have targeted regression coverage. A synthetic
  10,000-process chain solved in 0.2101 seconds after imports, with zero balance
  residual; this benchmark does not establish live pY physical performance.
- Full unlocked pY catalog validation now retains 1,041 researched technologies;
  the previous 256-row truncation and empty-Lua-array representation mismatch
  are repaired. Fresh pY UI receives 9,467 recipes + 679 explicit exclusions and
  648 machines. Latest sweep: 80 pages / 12.313 seconds; UI apply mean 31.837 ms,
  maximum 172 ms. First-capture tick-rate minimum 6.25: still an open issue.
- Background catalog pages are paced independently of status polling and resume
  after budget/concurrency pauses. A failed large sweep is retained as failed
  evidence; the subsequent combined test completed the catalog on the correct
  surface with zero bridge failures or rejected ticks.
- The combined five-minute disposable fresh-pY run passed: 59.89 average UPS,
  58.53 minimum, 0 samples below 58, 19 model responses, one governor deferral,
  no model errors, no fluid stalls, and zero observer failures/timeouts. Fixture
  receipts verify eight robot networks, 320 logistic + 200 construction robots,
  and contents in 24 wagons. Source save unchanged; test workers stopped.
- Dashboard evidence: 1,920 x 1,080 actual-data offscreen image, inspected with
  Pillow. Event-processing mean 3.518 ms / maximum 173.615 ms; peak child RSS
  325.88 MiB, peak CPU 100.8% where one core is 100%. These are not native FPS,
  VRAM or GPU measurements. The initial catalog-capture dip remains separate.
- Research, local-chunk pollution, delivered power and robot availability now
  reach the Overview. Missing/stale measurements clear rather than look current.
  Status failures reset tick ordering; non-status cache keys carry a recovery
  epoch. The loop-bound MCP session remains on its owning event loop.
- Factory Map now uses bounded user-driven chunk requests, shared UPS budgets,
  surface-isolated cache, validated raster decoding and observed entity layers.
  Live checking found and fixed the fast-status flag suppressing map terrain.
  Pillow found a second missing-ground rendering defect; a pixel regression and
  stronger live terrain assertion now cover it. Fresh pY rendered one observed
  64 x 64 terrain chunk plus entity primitives; unknown chunks remain blank.
- Fresh pY UI passes single/chain estimates, machine-layout draft codec round
  trip, real map data, telemetry context and disconnect planning invalidation.
  Blueprint routing and physical buildability are not certified by these tests.
- The new pY source save hash still matches
  `5f7da3d8d76572f2131fc4e4dff2c4d5756e4531c2be3a93c60dcaa288cd7dc4`.

Still open: advanced temperature/quality/productivity/module/beacon/fuel/spoilage
planning adapters; measured per-output physical production windows; connected
blueprint routing and real-client import fidelity; inventory spatial filtering;
initial catalog capture performance; native FPS/GPU and longer endurance evidence;
launcher migration and the user-reviewed H1 decision. The Qt shell is tested live
through acceptance harnesses; the default launcher remains Tkinter. No autonomy
expansion, broad cleanup, private-config checkpointing or publication is implied.


Final vanilla/Space Age parity also passed with the strengthened terrain check:
650 recipes + 12 explicit exclusions, 18 machines, six pages in 0.672 seconds;
UI apply mean 23.333 ms / maximum 47 ms. One observed terrain raster rendered.
Single/chain estimates, draft codec round trip, telemetry context and disconnect
planning invalidation passed. The gear estimate reported 77,500 W including
observed idle drain. There were too few distinct status samples to estimate UPS;
the UI correctly retained unavailable rather than inventing a value. The source
save was unchanged and both owned game processes stopped.

Checkpoint target: `refs/codex/helper-validated-20261028`. Its explicit source list
combines earlier helper/dashboard checkpoints with these verified repairs and
the approved dependency pins. Saves, private settings, logs, credentials and
unrelated worktree files are excluded. It is a private recovery checkpoint, not
a release or a claim that the large pre-existing worktree has been cleaned up.
