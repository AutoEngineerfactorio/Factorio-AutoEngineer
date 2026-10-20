# Zoo Code: Factorio 2.1.23 input helper + active development handoff

**Current target:** Factorio 2.1.23, not 2.1.22 and not 2.0.77. This handoff supersedes the older version-stamped 2.1.22 update assignment without deleting its historical evidence.

Read first:
- ROADMAP.md and LOCAL_AI_HANDOFF.md
- .clinerules/17-factorio-2-1-23-primary.md
- .clinerules/16-r05-regression-guard.md
- docs/FACTORIO_2_1_23_MIGRATION_2026-10-20.md
- docs/R05_MECHANICS_EVIDENCE_LEDGER.md

The exact game binary is D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe. Its verified ProductVersion is 2.1.23 even though one directory retains an old name. Do not move/rename an active game.

Use .local/launcher-profiles/2.1.23/launcher.local.json, .local/mod-test-mods/2.1.23 and factorio-mod/autoengineer-input_2.1.23. The 2.1.23 Lua helper now handles respawn via player_index, while preserving human input and per-player takeover epochs. The helper was tested in an actual 2.1.23 headless save and loaded without errors. tests/test_factorio_2123_api.py validates the newly installed API data.

Do not edit old versioned mod/profile folders, existing regular saves, user login, private passwords or historical R05 acceptance evidence. Do not auto-approve destructive Git resets/whole-file rewrites. Prefer one narrow change with a passing focused test and Ruff before full regression.

Do not claim R05/Phase 1A fully accepted merely because the mod loaded: a separate 2.1.23 connected-player read-only telemetry, power, status/reason, dashboard and R06 integration run remains to be performed. Retain Helper read-only mode and locked autonomy until the formal gates pass.
