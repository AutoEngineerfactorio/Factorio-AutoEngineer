# Verified starter mining and crafting — local validation

Added dashboard Mine/Craft modes, batch size 1–3, preflight and fresh approval, exact-tool one-use permits, backend lease/range/recipe/material checks, and independent inventory verification. Basic mining supports iron ore, copper ore, coal and stone within two tiles; no automatic travel. Crafting initially supports gears and copper cable from normal plates. One bounded batch per session; autonomous planning and full vanilla/Space Age recipe coverage remain later work.

Validation:
- 101 Python tests passed; separate Release backend built with zero warnings/errors.
- Combined policy-v5 patch applied to clean pinned upstream and reproduced tested sources.
- Live mining: two iron ore depleted and two inventory items gained, no player movement.
- Live crafting: two gears consumed four iron plates; three cable crafts produced six cables from three copper plates.
- Rejection: no operation dispatched.
- Live locked-recipe and missing-material preflight: no approval requested or action executed.
- Active Stop during both mining and crafting: observed active work, then mining false/queue empty and stopped lease.
- Parent-process kill during both: game-side lease expiry stopped work; all unfinished crafting inputs refunded and no extra products/ore gained. Process-kill runs correctly have no controller stop acknowledgement; stopped state was observed independently in game after three seconds.
- Pre-existing human craft preserved: busy preflight denied the agent batch, and cleanup left the human queue untouched; the test fixture was then cancelled/refunded manually.
- Navigation regression: approved two-tile objective still arrived under the updated tick handler (1.51-tile displacement, within tolerance), with stop acknowledgement.
- Four raw-backend negative requests (unsupported resource, count above cap, extra argument, wrong owner) denied; inventory and position unchanged.
- Actual dashboard mode selection and Approve action tested for two one-gear batches. Final verified inventory display matched four gears and twelve remaining iron plates. Stationary after cleanup over 183 advancing ticks.
- Original five-tile validator and SafetySession class ASTs unchanged; existing pathfinding source unchanged. Console prompt generalized from movement to action.

Tested in the same dedicated save, using isolated backend/configuration. Fixtures moved only the disposable player next to naturally existing ore and supplied crafting plates. Cable was initially locked: the production guard correctly refused it; it was temporarily enabled for the positive fixture and restored to disabled afterward. Mining/crafting speed was temporarily slowed for cancellation tests, then reset to the standard zero modifiers. Actual mined/crafted outputs and remaining test plates are retained in the test save. Main saves and license untouched.

Safety limits: Stop cannot undo completed items. Do not manually alter inventory, mining/selection or the crafting queue during an agent batch; stop before takeover. An empty crafting queue is required before dispatch. Cancellation handles the owned recipe/remaining approved batch, not unrelated queues. These are bounded starter operations, not unrestricted mining, construction, fluid extraction, smelting or recursive crafting. Inventory must fit the bounded complete main-inventory observation for independent verification. Process/connection loss uses advancing-tick lease expiry; actions can complete before expiry. Connection loss was not separately re-injected in this round; process-loss and explicit-stop cases were exercised live.

Recorded before publication. The bounded starter-operations milestone is complete; full vanilla/Space Age coverage and the Factorio-style dashboard upgrade remain unchecked Phase 3 work.
