# Restricted backend patch

Apply `backend-safety.patch` once to the pinned, separately obtained FactorioMCP checkout, revision `f2fca61707efe3107e7a3738bb83d1505b0126f7`. This combined patch supersedes the earlier safety-only patch; do not apply both. See [tested installation](../docs/PROTOTYPE_SETUP.md).

The patch includes session leases and game-side stopping, exactly twelve explicitly registered bounded gameplay/safety tools, a bounded read-only recipe/research adapter on `autoengineer_view`, a closed request filter, direct movement status, backend five-tile enforcement, environment-only password without fallback, no startup chat listener, and a NuGet lockfile. Broad tools/resources and the unused image dependency are removed from the restricted build profile. `SafetyTools.cs`, `AutoEngineerTools.cs`, and `Tools/RecipeResearchAdapter.cs` here are readable copies already included in the patch; do not add them twice.

The `autoengineer_view` read accepts `catalogPage` (1..10,000) and `catalogPageSize` (1..32; default 16). It returns same-tick game version, force, surface, researched technologies, active content, and supported recipe rows including the active recipe category, ingredients and products, plus total/page counts. Recipe category metadata is not a machine-to-category compatibility matrix. Names, ingredients, products, research, active-content, recipe-count and fingerprint work are bounded; the catalog caps at 10,000 names, with 32 content names, 256 researched names, 16 ingredients and 8 products per emitted recipe, plus 2 MB/100,000-node fingerprint limits. Unsupported recipe fields are omitted only while marking the page truncated. A partial catalog never certifies planner readiness. The offline Python observer assembles pages only when tick, version, force, surface, research, enabled content, counts, ordering and source fingerprint agree; research/content equality is checked directly, and live feasibility and latency are not verified. The explicitly labelled `poly31x131-v1` checksum is a stable change detector, not authentication. Catalog source/build/runtime compatibility and payload/latency limits still require verification against the pinned backend and exact Factorio runtime before use.

`BASELINE.json` identifies the upstream revision and hashes of changed original files, normalized to LF. The separately built backend retains its existing MIT license; [third-party notices](../THIRD_PARTY_NOTICES.md) reproduce it verbatim. Original additions retain the project MIT license. No vendor binaries or checkout are bundled. See the [implementation audit](../docs/DISPATCH_AUDIT.md) and [validation](../docs/HARDENING_VALIDATION.md). Existing backend tests for removed vision capabilities are not part of this restricted profile; the recorded checks cover compilation, dependency audit, Python tests and direct live dispatch denials.

Objective navigation requires the current policy-v8 patch and a rebuild. It validates returned Factorio paths before walking, including total planned length at most five tiles. See [objective navigation](../docs/OBJECTIVE_NAVIGATION.md). NavigationPathPolicy.cs is a standalone copy for the offline route tests; the combined patch already installs it.

The live dashboard requires policy v8 and the bounded, read-only autoengineer_view tool. Rebuild from the current combined patch on clean pinned upstream. See [live dashboard](../docs/LIVE_DASHBOARD.md).

Policy v5 adds only two closed starter-operation tools. The combined patch installs OperationService.cs and extends the guarded tick/Stop paths to bound mining and cancel unfinished owned crafting. See [verified operations](../docs/VERIFIED_OPERATIONS.md).

## Game-style dashboard display
Rebuild this patch for palette-indexed terrain and slot inventory. The read-only observer does not arm a gameplay lease. See [display setup and bounds](../docs/LIVE_DASHBOARD.md).

Operating modes are documented in [OPERATING_MODES.md](../docs/OPERATING_MODES.md). The current mode-aware backend must be rebuilt before Semi-Autonomous sessions run.

Normal-speed movement requires policy v8. Walking is steered on game ticks, with actual travel bounds and stopped-position arrival verification. `NavigationTick.lua` is a readable copy already included in the patch; do not install it twice. See [normal movement and hosting](../docs/NORMAL_MOVEMENT.md).
