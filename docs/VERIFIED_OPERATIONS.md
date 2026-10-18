# Verified starter mining and crafting

Select Mine or Craft in Session action, select an allowed resource/recipe, choose
a batch of 1–3, and start. Review the proposed batch, then Approve action, Reject
or Stop. Navigation remains a separate mode. Editing settings affects the next
session only. One approved batch runs per operation session; this is a development
step toward autonomous operation with human supervision, not an automatic planner.

Starter scope:
- Mine iron-ore, copper-ore, coal or stone already within two tiles. The preview
  binds the exact resource position; the operation never walks or mines buildings.
- Handcraft iron-gear-wheel or copper-cable from sufficient normal-quality plates.
  The recipe must be enabled and handcraftable. No intermediate auto-crafting,
  research unlocks, smelting, fluids, building, quality selection or other recipes.

Preflight rejects busy walking/mining/crafting, absent nearby resources, insufficient
materials and capacity, or locked recipes. A second preview after approval rejects
changed position, target or inventory baselines. Each write needs a one-use permit
bound to the exact tool and arguments, plus the owning safety lease. The backend
repeats preconditions after its queue wait. The host independently reads main
inventory before/after. Success requires exact product gain and exact ingredient
consumption, or ore depletion and inventory gain, not just a successful tool return.
Partial/invalid inventory observations cannot be used to verify a batch.

The game-side tick handler bounds mining by count, exact selected resource, range
and a 600-advancing-tick deadline. The owning lease must remain active. It stops
on completion, invalid target, timeout, Stop or lease expiry. Unfinished owned
crafts are cancelled on Stop/expiry and their remaining inputs are refunded by
Factorio. Already completed items are retained: Stop is not an undo operation.
Controller timeout is bounded independently. The existing five-tile movement and
path checks remain active for navigation; operation mode issues no movement.

Do not manually change inventory, mining, selection or the crafting queue during
a batch; use Stop before taking over. Operations require an initially empty queue.
Cancellation touches only the current owned recipe and at most its remaining
approved count; unrelated pre-existing queues are rejected, not adopted. The
single-actor assumption is part of verification: external/manual inventory or
queue manipulation can invalidate its accounting. Process/connection loss falls
back to the advancing-tick lease; actions may complete before expiry. Paused game
ticks do not advance that lease or the game-side operation deadline.

Rebuild the current combined patch against the pinned clean upstream. Policy v5
and exactly twelve tools are required, adding autoengineer_operation_preview
(read-only) and autoengineer_operation (approved write). OperationService.cs is
included by the patch; the standalone copy supports review. No arbitrary Lua,
spawn, research, teleport or general crafting/mining tool is exposed.

Console alternative: set AUTOENGINEER_OPERATION to JSON with exactly kind, name
and count, for example {"kind":"craft","name":"iron-gear-wheel","count":1}.
Omit that variable for normal navigation. This starter milestone does not claim
complete vanilla/Space Age recipe or mining coverage.

API semantics checked against the official Factorio LuaPlayer/LuaControl runtime
documentation: https://lua-api.factorio.com/latest/classes/LuaPlayer.html and
https://lua-api.factorio.com/latest/classes/LuaControl.html.
