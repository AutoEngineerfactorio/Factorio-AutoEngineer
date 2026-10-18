# Restricted backend patch

Apply `backend-safety.patch` once to the pinned, separately obtained FactorioMCP checkout, revision `f2fca61707efe3107e7a3738bb83d1505b0126f7`. This combined patch supersedes the earlier safety-only patch; do not apply both. See [tested installation](../docs/PROTOTYPE_SETUP.md).

The patch includes session leases and game-side stopping, nine explicitly registered bounded tools, a closed request filter, direct movement status, backend five-tile enforcement, environment-only password without fallback, no startup chat listener, and a NuGet lockfile. Broad tools/resources and the unused image dependency are removed from the restricted build profile. `SafetyTools.cs` and `AutoEngineerTools.cs` here are readable copies already included in the patch; do not add them twice.

`BASELINE.json` identifies the upstream revision and hashes of changed original files, normalized to LF. The separately built backend retains its existing MIT license; [third-party notices](../THIRD_PARTY_NOTICES.md) reproduce it verbatim. Original additions retain the project MIT license. No vendor binaries or checkout are bundled. See the [implementation audit](../docs/DISPATCH_AUDIT.md) and [validation](../docs/HARDENING_VALIDATION.md). Existing backend tests for removed vision capabilities are not part of this restricted profile; the recorded checks cover compilation, dependency audit, Python tests and direct live dispatch denials.

Objective navigation requires the current policy-v5 patch and a rebuild. It validates returned Factorio paths before walking, including total planned length at most five tiles. See [objective navigation](../docs/OBJECTIVE_NAVIGATION.md). NavigationPathPolicy.cs is a standalone copy for the offline route tests; the combined patch already installs it.

The live dashboard requires policy v5 and the bounded, read-only autoengineer_view tool. Rebuild from the current combined patch on clean pinned upstream. See [live dashboard](../docs/LIVE_DASHBOARD.md).

Policy v5 adds only two closed starter-operation tools. The combined patch installs OperationService.cs and extends the guarded tick/Stop paths to bound mining and cancel unfinished owned crafting. See [verified operations](../docs/VERIFIED_OPERATIONS.md).
