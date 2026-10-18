# Development roadmap

This is a planning roadmap, not a promise of release dates.

## Phase 0 — Tested proof of concept
- [x] Local LLM responds via llama.cpp
- [x] Connect Python MCP client to FactorioMCP
- [x] Read live player state
- [x] AI proposes and validates a movement
- [x] Execute supervised movement and verify position
- [x] Basic desktop UI approvals and logs

## Phase 1 — Safe, reproducible development release
- [x] Audit tool implementations and establish a strict dispatch boundary
- [x] Replace temporary RCON credentials and isolate configuration
- [x] Address dependency vulnerability warnings
- [x] Package only authorized project source, with tested installation instructions
- [x] Detect stalled, repeated, and failed movements reliably
- [x] Add concise, structured agent event logs

## Phase 2 — Intelligent exploration
- [x] Persistent visited-area and failed-target map
- [x] Objective-based navigation and path validation
- [ ] Efficient discovery of nearby resources
- [ ] Live 2D dashboard map and inventory display

## Phase 3 — Factory gameplay
- [ ] Verified mining and crafting operations
- [ ] Resource-aware factory building and placement checks
- [ ] Production, power, research, and recovery planning
- [ ] Human/AI task handoff

## Phase 4 — In-game companion
- [ ] Compact, expandable Factorio UI panel
- [ ] In-game plan visualization and status
- [ ] Manual pause/takeover and optional assistance
- [ ] Evaluate separate-player cooperative control feasibility

## Phase 5 — Modded gameplay and autonomy
- [ ] Runtime discovery of modded prototypes and recipes
- [ ] Validate Space Age and selected overhaul mod compatibility
- [ ] Safe unattended execution with budgets, watchdogs, and recovery
- [ ] User-friendly packaging and onboarding
