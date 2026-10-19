# AutoEngineer project guidance for Cline

Read LOCAL_AI_HANDOFF.md, ROADMAP.md (complete R01-R20 index), and docs/PLANNING_REQUIREMENTS.md before a task. For gameplay features consult docs/FACTORIO_MECHANICS_REFERENCE.md, docs/FACTORIO_QUIRKS_AND_EDGE_CASES.md and docs/FACTORIO_COVERAGE_GAP_REGISTER.md; for Lua/mod API features also consult docs/FACTORIO_SCRIPTING_API_REFERENCE.md and the exact versioned official runtime/prototype API. Treat documented quirks as unverified candidates until backed by game evidence. Never expose arbitrary Lua/RCON to the AI or change gameplay permissions. R01-R03 have tested local foundation scope. R04-R05 source and offline checks were published, with broader live acceptance still open; R06 development is underway. The roadmap continues through R20 (R07-R19 planned, R20 third-party mods last); milestone acceptance, public onboarding and endurance gates remain open.

Use explicit attached files and one bounded task. Never repeat an identical search after receiving its result. If evidence or a file is missing, say so and stop. Do not invent a completed feature, bug, recipe or successful test. Report file/function evidence and actual test results.

Use Plan mode for advisory reviews. Keep edits, commands and tool actions subject to approval; never enable blanket auto-approval to work around a loop. Review generated patches and run the relevant deterministic tests. A model response does not verify gameplay.

Preserve human approval, emergency stopping, normal game speed, the five-tile movement limit and locked Full Autonomy. Use only the established disposable save when the human authorizes a game test. Space Age is vanilla; third-party gameplay mods come last. Preserve MIT and backend attribution.

Never read ignored private files, saves, credentials or weights. Never operate the game, approve gameplay, publish, or message anyone on your own. Publication is handled separately by the human-authorized workflow. No cloud provider or credentials should be changed as part of a code review.
