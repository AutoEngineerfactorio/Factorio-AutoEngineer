# Factorio AutoEngineer — ChatGPT Work Handoff

> Reconciled with published commit `099a4de93a76a48c2c81758521d7a519c1f66391` on 2026-10-18. This is planning context, not execution authorization. Phase 0–2 are complete at their documented scope; bounded starter mining/crafting is tested and published. Full vanilla/Space Age operations, the Factorio-style map and player-style inventory remain pending in Phase 3. See [current roadmap](../ROADMAP.md) and [validation record](VERIFIED_OPERATIONS_VALIDATION.md).
>
> Historical research claims below (model/GPU releases, Factorio 2.1, mod versions, mechanics and licensing) have not been independently verified in this reconciliation. They are research leads, not supported compatibility claims. Verify primary sources before implementation. Referenced addenda not included in this repository are unavailable context. No game, mod, save or license changes are authorized by this document.

**Prepared:** 2026-10-18  
**Purpose:** Paste or attach this to the separate ChatGPT Work conversation on the Windows PC.  
**Current state:** Planning/inspection only. Nothing in this handoff authorizes unattended changes, downloads, installs, save edits, game actions, or GitHub publication.

## Mission
Build a Windows-first, open-source **Factorio AutoEngineer** that acts as a legitimate/no-cheat AI player and optional cooperative teammate. Preserve **supervised autonomy** during development, with full autonomy as the eventual goal. Players must be able to take over, assist the AI, issue goals, inspect reasoning summaries, and stop actions from both an external dashboard and an expandable in-game panel.

Public organization: https://github.com/AutoEngineerfactorio  
Expected main repository: https://github.com/AutoEngineerfactorio/Factorio-AutoEngineer  
FLE research reference only: https://github.com/JackHopkins/factorio-learning-environment  
Third-party FactorioMCP upstream: https://github.com/sbarisic/FactorioMCP

## Current implementation and privacy
- Strict policy-v5 dispatch exposes 12 audited tools, not the historical unrestricted 116-tool inventory.
- Movement progress, blocked routes, emergency stopping, exploration memory, objective navigation and resource discovery have published validation records.
- The live dashboard map is schematic and inventory is text-based; the game-style upgrade is pending.
- Starter operations cover bounded basic ores, gears and cable only. They do not establish a complete beginner factory or autonomous playthrough.
- Use repository example configuration and a single dedicated disposable test save. Machine-specific paths, private hardware inventory and local service details were removed from this public handoff. Never publish credentials, personal saves or proprietary game assets.

## Priority A — Read-only installation and source audit FIRST
1. Confirm authorized Windows computer access; if unavailable, request access rather than claiming to have inspected the PC.
2. Inspect the current project tree, running services, `git status`, tracked/untracked files, and relevant configurations. Do not reset, delete, commit, push, or overwrite.
3. Inspect existing `autoengineer_dashboard.py`, `supervised_agent.py`, `ai_movement.py`, FactorioMCP launch/configuration, third-party licenses, and docs. Identify what is owned code versus upstream code.
4. Confirm dependency warnings from `SixLabors.ImageSharp 3.1.12` (NU1902/NU1903 from prior builds); propose safe mitigation, avoid blind package upgrades.
5. Review console stdout/stderr integrity of C# MCP host, credential handling, game process shutdown, RCON isolation and existing saves/mod profiles.
6. Report findings, blockers, precise changed-file proposal, risks and validation steps. **Ask approval before making changes.**

## Priority B — Windows AutoEngineer.exe dashboard + launcher
- Preserve the functioning Tkinter UI initially; package with PyInstaller into a **one-folder** Windows distribution for testing, then consider one-file installer.
- Startup wizard: detect Factorio executable, version, Steam/non-Steam install, DLC and mod profile; choose isolated server save and client profile.
- Manage or **attach** separately to: local inference runtime (llama.cpp or alternative), dedicated Factorio server, MCP controller, and graphical game client.
- Avoid duplicate processes, port conflicts, and unsafe forced termination. Only stop AutoEngineer-owned processes and ask before closing active games.
- Track health status and errors; do not mark readiness until model API, RCON/MCP and game connect correctly.
- UI panels: **live map** (player, visited tiles, scanned/known resources, structures, planned destinations); **inventory/recipes**; **objectives**; **proposals and approvals**; **event and error logs**; **start/pause/resume/stop**; provider/model choice; performance.
- Show which data is observed versus inferred. Sanitize logs. No raw API keys/passwords.
- Build a typed event/telemetry bus shared by GUI and (later) companion mod.

## Priority C — In-game cooperative AI panel
- Expandable compact panel in Factorio corner with status, current objective, activity, command field, takeover/pause and approval prompts.
- Player can contribute resources or building effort, set goals, or temporarily take manual control.
- **Initial design is shared-character turn-taking.** Genuine simultaneous player + AI avatars requires a separate technical feasibility audit.
- Prefer Factorio-supported GUI/render APIs; avoid gameplay cheats, unsupported game internals, or unrestricted remote-code execution.
- Verify multiplayer/mod requirements, server-client synchronization, and UI interaction safeguards before implementing.

## Priority D — Model/runtime choice and GPU-aware recommendations
Implement adapter interface: `list_models`, `health_check`, `generate_structured_decision`, `cancel`; require strict schema validation, timeouts, token budgets, logging without secrets and model-independent gameplay rules.

- Local: **llama.cpp Vulkan** (verified on owner's AMD card), then LM Studio / OpenAI-compatible HTTP; optional Ollama for others, **not required**. CUDA for NVIDIA where supported; Vulkan/SYCL candidates for Intel as verified.
- Cloud (optional): OpenAI, Gemini, Claude, Mistral, DeepSeek, OpenRouter; users provide credentials, clear cost warnings. Do not confuse a ChatGPT subscription with API entitlement.
- GPU detection must use exact device and **free dedicated VRAM**, not just advertised capacity. Account for model weights, KV cache/context, runtime, OS graphics and Factorio; test while the game runs.
- Profiles by dedicated VRAM (all candidates until tested):
  - **12GB:** Qwen2.5-Coder-7B Q4 (~4.7GB weights; **only working baseline**); Qwen3 8B Q4; Qwen3.5 9B Q4; Ministral 3 8B; Granite 4.2 8B and Gemma 4 small family as *newly identified research candidates*.
  - **16GB:** Qwen3 14B Q4; Qwen2.5-Coder 14B Q4; Ministral 3 14B; Gemma 3 12B; newer Gemma 4 12B as research candidate.
  - **24GB:** Mistral Small 3.2 24B Q4; Gemma 3 27B Q4; **LFM2.5-24B-A2B Q4** (~14.5GB file as previously reported; verify official card); Qwen3 32B Q4 and Qwen3.8 27B Q4 only after real headroom checks.
  - **32GB:** Qwen3 32B Q4/Q5, Gemma 3 27B; research Qwen3.6 35B-A3B and Qwen3.8 27B.
  - **48GB+:** Qwen3 32B higher precision; quantized 70B-class models if ample *actual* free VRAM. Qwen2.5 72B Q4 at 48GB is **not** a safe default while Factorio runs; 64GB+ preferable.
  - Handle **20GB, 28GB, below 12GB, multi-GPU, CPU partial offload and remote-server** configurations dynamically.
- Example GPUs for reference:
  - 12GB: RX 6700 XT/6750 XT/7700 XT; RTX 3060 12GB/4070/5070; Arc B580.
  - 16GB: RX 7800 XT/7900 GRE/9060 XT 16GB/9070/9070 XT; RTX 5060 Ti 16GB/5070 Ti/5080; Arc A770 16GB/Pro B50.
  - 24GB: RX 7900 XTX; RTX 3090/3090 Ti/4090; Arc Pro B60.
  - 32GB: RTX 5090, Radeon AI PRO R9700, Radeon PRO W6800/W7800 32GB.
  - 48GB+: Radeon PRO W7900, RTX A6000, RTX 6000 Ada, RTX PRO 5000/6000 Blackwell workstation variants.
- Verify exact SKUs, availability, GGUF/runtime support and licenses from primary sources. **Do not claim newer model announcements are confirmed without checking the developer's official release and weights.**
- AutoEngineer compatibility levels: `research candidate`, `download/loader verified`, `structured action suite passed`, `gameplay tested`, `community stable`. No blanket 'compatible' claim based on GPU VRAM alone.

## Priority E — Autonomous gameplay reliability and learning from FLE
- Study https://github.com/JackHopkins/factorio-learning-environment as **research inspiration only**: observation/action/reward or result feedback, reproducible evaluation tasks, efficient telemetry, model-independent experiments. **Do not copy its code**.
- Deterministic exploration frontier/grid with persisted visited patches and resource scans; model selects meaningful goals, controller performs safe navigation. Avoid oscillation and repeated already-within-tolerance moves.
- Strict allowlist gateway for `get_player_position`, `get_inventory`, `scan_resources`, `find_nearest`, `get_recipe_details`, `check_craft_feasibility`, `walk_to_position`, `mine_resource`, `craft`, then placement tools only after audit.
- AI **never** gets `execute_lua`, unrestricted RCON, host shell, teleport, item spawning or game-state cheats.
- Validate inputs against live state: finite coordinates, reachable/ranged targets, positive bounded quantities, valid prototypes, inventory, ingredients, available recipes and mod changes.
- Verify outputs including actual *progress*, resource/inventory deltas, craft queue results, error status, and recovery; cap action count and retry count.
- Add mod-aware prototype mapping and recipe dependency planning; prioritize normal early-game work before Space Age or overhaul mods.
- Build regression/evaluation suite: valid JSON, correct allowlisted tool, exploration progress, physical movement, legitimate ore acquisition, feasible craft, first furnace/inserter/power line, no duplicate actions, safe manual takeover, resource and performance budgets.

## Priority F — Open-source website, repo and release
- Public repository: https://github.com/AutoEngineerfactorio/Factorio-AutoEngineer — user confirmed it exists.
- Starter docs (README, ROADMAP, CONTRIBUTING, .gitignore, docs/index.html) were prepared in chat earlier; **verify whether uploaded before editing**.
- Separate our original source from upstream FactorioMCP. Audit redistribution, attribution and licenses; do not assume third-party code may be republished.
- No private saves, model weights, secrets, local GGUF caches, commercial Factorio game binaries or proprietary assets in Git.
- Create GitHub Pages documentation with transparent statuses, prerequisites, screenshots, runtime selection, how to test/revert, license and security disclosure.
- Use a reviewable branch/PR or diff preview. **Do not push, create a release, change repository visibility, or enable Pages without explicit user approval.**

## Newly announced AI releases — verification queue
A prior conversation surfaced the following names; these are **research leads, not confirmed compatibility**. Check the latest official developer announcements, model cards, licenses and actual downloadable formats before adding them to a published compatibility table:
- Liquid AI **LFM2.5-24B-A2B** (agent/on-device candidate)
- IBM **Granite 4.2 8B** and **Granite Switch 4.1**
- **Qwen3.8 27B**, **Qwen3.6 35B-A3B**
- **Gemma 4** E4B/12B/26B/31B variants
- New cloud-agent models and future Mistral open-weight announcements as verified.

## Release watch / recurring updates
A recurring **AutoEngineer AI Release Watch** is set up in ChatGPT to check daily for meaningful new model/runtime releases. It will notify the user **only when a relevant development appears**, cite source links, map to GPU tiers and suggest GitHub documentation updates. **It will not automatically edit the repo or install models.** The Work session should request the latest watch findings if they are needed and available; never invent that a notification was received.


## Blueprint production optimization — new priority
**Core requirement:** blueprints must be derived from live game/mod recipe data and validated mathematical production flow; do not let an LLM invent machine ratios or free-form blueprint strings. Build a deterministic recipe graph + machine throughput + belt/inserter/pipe/power + spatial layout optimizer, with explicit target items/minute, material BOM, bottleneck analysis, headroom/utilization and blueprint revision history. Separate ideal capacity from real sustained throughput. The model chooses objectives and explains trade-offs; the solver produces candidates and the game validates construction/actual rates. Start with 300 iron gears/minute benchmark (5 assembler 1 machines theoretically, 10 iron plates/second; 6 assemblers for illustrative 85% utilization margin), then modded and Space Age cases. See `AutoEngineer_Blueprint_Math_Recipe_Optimization_Addendum.md`. **No implementation or GitHub changes until specifically approved.**

## Work-session order and deliverables
**First session (after approval to make changes):**
1. Read-only audit and source/dependency/license inventory; present summary and request approval.
2. Formalize app architecture and package boundaries (dashboard, launcher, provider adapters, safe-game gateway, companion mod).
3. Build a **launcher prototype** for existing llama.cpp and Factorio test profile with start/attach/status/stop lifecycle and no duplicated servers; smoke test.
4. Add GPU detection and local/provider configuration editor, using *verified* inference interfaces.
5. Make an initial PyInstaller one-folder `AutoEngineer.exe` test package; reproduce start, attach and shutdown safely.
6. Implement structured event logging and a live position/inventory panel before a full map.
7. Independently design FLE-inspired acceptance tests; plan the companion mod feasibility phase.
8. Prepare doc/compatibility updates as a diff or PR draft, **ask before publishing**.

**Acceptance criteria for first build:** user launches the dashboard from Windows; picks a known model; sees services' actual status; connects to isolated test save; observes position and inventory; reviews an AI action; approves one movement; sees verified progress or actionable failure; can stop agent without corrupting saves or killing unrelated applications.

**Do not do tomorrow without specific additional approval:** mass mod installation, changes to personal saves, any raw arbitrary Lua execution, installing new GPU drivers, public release uploads, repository pushes, broad tool grants, automatic play of the user's main save.

## How to use this handoff
1. In ChatGPT **Work mode on the Windows PC**, attach this `.md` file.
2. Paste the separate `AutoEngineer_Paste_Into_ChatGPT_Work.txt` kickoff message.
3. Let Work perform **read-only discovery first**, then review its exact proposed file changes before approving.
4. Keep this handoff as project context, not a substitute for inspecting actual current files.

## Helmod-inspired megafactory, combinator and train planning — added 2026-10-18
**New core requirements:** Use Helmod-style multi-product recipe/rate calculations as a research reference, but independently implement a deterministic megafactory solver able to partition high-complexity modded production chains into scalable factory blocks. Incorporate Factorio 2.0 constant/arithmetic/decider/selector combinators as a compiled typed circuit plan for inventory control, recipe switching, power and demand signaling. Make rails, signals, fuel, loading/unloading, station priorities and schedule interrupts first-class capacity-constrained logistics; support LTN/Cybersyn 2 as *optional* mod-specific integrations when installed. Include throughput, build cost, power, space, UPS, reliability and expansion in candidate evaluation. The selected LLM chooses goals/trade-offs, not recipes/ratios/wiring invented from memory. Validate based on actual 2.0.77 game/mod prototypes, test in an isolated save, and require approvals before installation, changes or publishing. See `AutoEngineer_Helmod_Megafactory_Circuit_Train_Addendum_2026-10-18.md`.

## Additional engineering requirements — bot fleets, combat and Factorio 2.1 experimental

Add robot-aware construction and logistics efficiency to the Helmod-inspired production/circuit/train/megafactory architecture. A construction robot job requires researched/available robots, legitimate materials, reachable ghost targets, roboport coverage and charging. Logistic robot operation must account for item payloads, roundtrip and charging time, network congestion, and UPS, using local networks connected by trains for long-distance bulk traffic. Support provider/requester/storage/buffer chest and combinator logic based on observed technologies and actual prototypes.

Combat robots are separate capsule-deployed temporary defenders/distractors/destroyers, **not** roboport logistics robots. New narrowly scoped use-item actions, if needed, require source/legitimacy/security audit and explicit supervised battle approval. Never give model `execute_lua` or game cheats.

Factorio 2.1 **experimental is released**, but it must be a separate later compatibility track. Maintain existing Factorio 2.0.77 test baseline; game version, save, blueprint, mods, API and new Space logistics features must be separately validated. **2.1-upgraded saves and blueprints cannot be downgraded to 2.0**, per Wube. Do not enroll in beta, install 2.1, convert saves, or touch Steam settings without specific user approval.

Read the detailed `AutoEngineer_Robots_Combat_Logistics_Factorio_2_1_Addendum_2026-10-18.md` for interfaces, formulas, UI, risks and acceptance tests. This is **planning only**, and changes must be approved before implementation.


## Space Exploration, researched combat, base defense and biter eggs — added 2026-10-18

**New requirements:** Add **Space Exploration** as an important independent mod compatibility target for planetary operations and industrial logistics. Implement a capability registry that reads the running game's *actual* researched technologies, recipes, weapons, ammo, vehicles, turrets, combat robots, armor, modded prototypes, enemies and surfaces. Use only capabilities genuinely available in the active game; plan research and manufacturing for locked equipment. Build mathematically justified base defenses with walls/turrets/ammo/power/repair bots/circuits/trains, threat sensors, mod-aware resistance checks, defense priorities, and supervised combat. Preserve player takeover and no-cheat action enforcement.

**Important game-profile incompatibility:** Space Exploration's mod metadata explicitly conflicts with the `space-age` built-in mod. Space Exploration v0.7.63 (2026-10-15 changelog) requires Factorio **2.1.22+**, while earlier v0.7.57 targets **2.0**. Keep the existing Factorio 2.0.77 Space Age test setup untouched. Add **separate** optional SE profiles, with independently pinned Factorio/mod versions and saves, only after explicit approval.

**Egg feature distinction:** Native **biter eggs and captive spawners are Space Age features**, not automatically present in stock SE. The experimental third-party 2.1 mod `sei-captive-biters-2` can bring capture robots/eggs/bioflux into SE, but conflicts with the official Space Age expansion and must be separately tested. In Space Age, require researched capture equipment; legitimately capture a living nest with a capture-bot rocket; sustain bioflux delivery, measure eggs and spoilage, protect the nest and base, and alert on starvation, reversion or spoiled eggs spawning biters. Never exterminate every nest if egg production or research will require some. Verify actual runtime rates, recipes and mod availability; never spawn egg items.

**Licensing and safety:** Space Exploration is distributed under a limited redistribution license. Don't bundle it with AutoEngineer, don't copy its code/assets, and don't publish private saves/credentials. Require explicit approval before installing/changing mod profiles, migrating saves, performing live combat or publishing Github changes. See `AutoEngineer_Space_Exploration_Combat_Biter_Eggs_Addendum_2026-10-18.md` for research, architecture, tests and official links.


---

# FULL AUTONOMY ROADMAP UPDATE — 2026-10-18

This is an extension of all previous requirements, not a replacement. The key newly audited gaps are end-to-end science/victory progression, robust recovery from failures/restarts, legitimate map visibility, power/fluid/temperature/perishables, separate Space Age platforms and Space Exploration spaceships, quality chance/recycling mathematics, and measurable endurance testing.

**Read the enclosed [full-autonomy gap audit](FULL_AUTONOMY_GAP_AUDIT_2026-10-18.md) for full architectural requirements, links, and G0–G9 acceptance criteria.**

**Reconciled near-term priority:** build the pending Phase 3 dashboard upgrade and legitimate beginner-factory progression on the tested controller. Launcher packaging remains Phase 5 work; do not repeat completed Phase 1/2 tasks. Do not attempt SE spaceship building or unattended megabase before validated beginner-factory and research milestones. Keep Factorio 2.0.77+Space Age as the existing working isolated profile, and separate 2.1 / SE tests. No changes without explicit approval.
