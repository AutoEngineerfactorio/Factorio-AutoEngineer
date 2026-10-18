# Efficient resource discovery — local validation

Session-local cache reuses the existing 50-tile scan for less than ten seconds and less than eight tiles from its origin. Empty scans are cached too. Resource summaries are validated, ranked by current center distance, copied on return and capped at 128 types. The log shows cache freshness, age, counts and nearest named centers. No new backend tool or dependency.

Validation:
- All 80 Python tests passed, including six new cache tests covering reuse, movement/time refresh, empty results, invalid data, isolation and resource names.
- Same dedicated saved Factorio world and persistent map ID reused.
- Read-only live probe: three observations required one actual scan and two cache hits; player stationary.
- Live Qwen objective navigation: three verified approved short moves used two fresh scans and one cache hit.
- Reject test: one approved move followed by two rejected proposals; no further dispatch, including with cached data.
- Active Stop test: stopped after .39 tiles; confirmed stationary with zero drift over 180 advancing ticks.
- All live controller sessions exited normally and acknowledged game-side stop.
- Independent five-tile validator AST unchanged; policy-v3 backend, watchdog and emergency-stop implementations unchanged.

Test harness approvals were supplied under the user's existing authorization for disposable-world testing. Production still requires human approval. Main game untouched; results recorded before publication.

The catalog describes resource-type bounding centers, not connected deposits or closest resource tiles. Cached coverage is the old scan circle; newly visible edge resources and depletion can remain unseen until refresh. Efficiency measurements count scan calls, not engine frame-time. Cache resets on each session and is not persisted across worlds.

Roadmap scope: Space Age is included in vanilla scope, with planet/platform/logistics/progression and quality/spoilage/elevated-rail coverage before modded support. Modded remains last. Resource discovery is complete after the offline and live checks above.
