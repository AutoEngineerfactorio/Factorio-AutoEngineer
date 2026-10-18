# Persistent map live validation

Tested local work/hardening agent against the separately patched backend and the existing isolated uncleared Factorio world. No main save used; nothing published.

1. Human approved Qwen coal target (0.1411, -3.9975), about four tiles from origin. Backend returned no_path; no movement. Map stored origin as visited and coal endpoint as failed. While approval was pending, independent observation confirmed player remained at origin.
2. Restarted the agent with the same world ID. Both records loaded. Failed coal target and nearby north waypoint were absent from real Qwen choices. Human approved iron target (1.9012, -3.5193), about four tiles. Verified arrived at (2.4140625, -3.046875), displacement 3.89 tiles; final cell persisted.
3. Restarted again without resetting player or memory. Both visited cells and the failed target loaded. Sent Stop at the normal approval prompt; no third movement dispatched. All three sessions confirmed game-side stopping and zero drift across 183 advancing ticks afterward.

Independent map checks confirmed both visited positions and failed endpoint after a full test-world save/reload. Existing five-tile validation and dispatch gate remained active; no bypass, auto-approval or runtime source changes were used. The wrapper limited each real-Qwen session to one proposal and printed offered choices for inspection.

Reuse the existing dedicated disposable test save, with the same AUTOENGINEER_WORLD identifier. The local test launcher now prefers this save. A missing isolated save-output directory caused the first save attempt to terminate the test server; created the directory, successfully saved and reloaded the dedicated world. No fresh map generation was needed. Lua acknowledgement persistence is expected with the saved world; no interactive Lua console prompt was exercised in this RCON-based test.

Offline validation remains 66 passing tests. Live Stop was tested while awaiting approval; earlier emergency-stop tests cover active motion/process loss. Persistent memory is manual-world-scoped and single-writer. No automatic terrain/path guarantee.
