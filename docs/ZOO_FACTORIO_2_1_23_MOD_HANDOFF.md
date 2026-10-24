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

## Verified registered player commands

The 2.1.23 input helper registers two player-facing commands:

- `/autoengineer-status` reports that the input guard is active and shows its takeover generation. It does not change game state and does not prove that the AI backend is connected.
- `/autoengineer-takeover` requests human control and increments the takeover generation once. Use it only when the player requests takeover, or in a separately authorized disposable test. Never send it automatically or retry it after a delayed response.

For graphical acceptance, first confirm the approved isolated Factorio 2.1.23 profile, open the game console, and enter `/autoengineer-status` once. Read the actual response and verify the input guard is available. A delayed response is not a reason to repeat the command. The status command does not require `/c` or Lua confirmation; ordinary first-use Lua confirmation remains required for arbitrary console scripting.

Registered player commands and RCON are separate interfaces. An RCON invocation may have no player index, so it is not a replacement for these commands. Keep the restricted policy-v8 backend for bounded telemetry, catalog, lease, policy, and owner-checked stop operations; do not expand its twelve-tool boundary. In particular, `/autoengineer-status` does not replace `autoengineer_view` or `autoengineer_policy`, and neither command provides production, power, recipe, research, force, surface, or backend-connection telemetry.

Do not edit old versioned mod/profile folders, existing regular saves, user login, private passwords or historical R05 acceptance evidence. Do not auto-approve destructive Git resets/whole-file rewrites. Prefer one narrow change with a passing focused test and Ruff before full regression.

Do not claim R05/Phase 1A fully accepted merely because the mod loaded: a separate 2.1.23 connected-player read-only telemetry, power, status/reason, dashboard and R06 integration run remains to be performed. Retain Helper read-only mode and locked autonomy until the formal gates pass.
