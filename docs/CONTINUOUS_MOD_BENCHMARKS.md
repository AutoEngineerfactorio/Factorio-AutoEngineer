# Continuous modded-recipe benchmarks — October 19, 2026

**Decision:** Use Pyanodons (pY) as a *continuous development benchmark* for the telemetry, dashboard and AI Helper, not just as a final modded-game test. Keep actual pY gameplay in a separate, isolated Factorio profile and save. The vanilla/Space Age profiles remain independent baselines.

This decision **does not** mark R04–R06 complete, authorize installing pY, or move live third-party gameplay compatibility ahead of R20. We can test data structures and planning complexity early while reserving authenticated live-mod support, legal in-game execution and compatibility claims for version-specific evidence.

**Version targets:** Develop against Factorio **2.1.22** as the primary target and
preserve **2.0.77** as an explicit backport target. Keep separate game installs or
profiles, mod directories and saves. Exact-version source gates and offline contracts
are being added for both; they do not replace builds against each runtime, clean
backend-patch reconstruction, or isolated live read-only acceptance. Do not migrate
or overwrite a 2.0.77 save to validate 2.1.22.

## Benchmark ladder

| Layer | When | Evidence to record |
| --- | --- | --- |
| Factorio 2.1.22 primary / 2.0.77 backport | Each R04–R06 change on both targets | Installed version, enabled content, observed recipe/research fingerprints, expected/actual math, test result; never infer runtime compatibility from offline tests alone |
| Synthetic pY-shaped recipe graphs | Each graph/solver change | Deterministic fixture version, 100/1,000/10,000 nodes, traversal latency, peak memory, cycles, missing references, truncation |
| Sanitized real pY catalog | Once user-approved read-only export exists | Exact Factorio/pY version and mod list, snapshot rights, page counts, fingerprints, unlock/availability states, byproducts and alternate routes |
| Live isolated pY gameplay | Only after relevant safety/adapter qualification | Save/profile, RCON/backend policy, tick/UPS, observation freshness, UI responsiveness, predictions versus measured outcomes |
| Space Exploration | Separate compatibility profile and phase | Surface/spacecraft/logistics differences; do not combine with pY by default |

### Instrument continuously

1. **R04 Telemetry:** Catalog paging and stable provenance; no silent clipping of a large modded recipe tree. Record game tick, research, surface, mod fingerprint, redacted observation metadata, completeness, time to read and missing/unknown fields. Reject stale or partial catalogs.
2. **R05 Dashboard:** Refresh latency, UI responsiveness, memory use and offline/disconnected warnings. Distinguish *observed*, *estimated* and *unavailable* information.
3. **R06 AI Helper:** Deterministic demand/rate planning, multiple production paths, catalysts, multi-output ratios, byproducts, fluid temperatures, recycling/loops, research and machine restrictions, power and logistics budgets. Compare solver results with controlled reference cases. No model-generated guess substitutes for math.
4. **R07/R08 blueprint readiness (after their gates):** Round-trip serialization, prototype availability, actual research, placement feasibility and material bills; no ghost/entity creation in Helper mode.
5. **Performance:** Compare a fixed machine, Python release and dataset hash with repeated runs. Report wall-clock/peak memory and correctness separately; don't claim throughput solely from a generated plan.

### Offline executable fixture

The checked-in `benchmarks/modded_recipe_graph.py` drives the **existing** R06 graph walker, not a separate production solver. It deliberately generates a **synthetic** wide graph with alternate branches, byproducts, a missing raw source and cycles. It does not import Pyanodons recipes, prove pY balance or run Factorio.

```powershell
python -m unittest tests.test_modded_recipe_graph_benchmark
python -m benchmarks.modded_recipe_graph --sizes 100 1000 10000
```

The JSON result records total graph nodes, cycles, truncation, construction/traversal milliseconds and peak Python allocation. Add measured budgets after several runs on the same machine; do not invent pass/fail speed thresholds. Archive summarized reports **without** saves, secrets, game logs or copyrighted modpack assets.

### Isolated runtime layout (future, not created by this document)

- Primary: a designated Factorio 2.1.22 profile with recorded patch version and a disposable save.
- Backport: a separate Factorio 2.0.77 profile and disposable save. Keep both until runtime and safety regressions pass independently; do not auto-migrate saves.
- pY: a separate game mod directory, config/write-data directory and save under a pinned *compatible* Factorio build. Check official compatibility for each pY dependency.
- Space Exploration: a distinct test profile, not mixed into the pY benchmark.

Each real profile has its own mod list, resolved versions, runtime fingerprint, fixtures and metrics. The AI Helper should adapt to loaded prototypes rather than hardcoded vanilla/pY names.

### Gates and interpretation

**Priorities:** 1. Telemetry/data truth, 2. reliable dashboard, 3. AI Helper/blueprints. Semi-Autonomous remains controlled and Fully Autonomous stays locked. R07 remains blocked by `docs/R04_R06_PRE_R07_ACCEPTANCE.md`; R20 still handles full third-party gameplay compatibility after vanilla and Space Age gameplay completion.

**Current evidence:** Synthetic benchmark and offline unit tests only. Actual Pyanodons installation, 2.1 upgrade, real modded telemetry, blueprint generation and long-running live tests have **not** been performed as part of this change.
