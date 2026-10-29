"""Contract tests for the R06 game-side live verification harness.

The harness itself starts a Factorio server and performs real in-game
crafting, so it is never executed by the offline suite. These tests assert
its safety contract statically: the source save is only ever read, the
restricted tool boundary is not bypassed, and the craft cases stay inside
the backend's own bounded allowlist.
"""

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

HARNESS = ROOT / "tests" / "live_r06_game_side_verify.py"
OPERATION = ROOT / "backend-safety" / "OperationService.cs"


def _tree() -> ast.Module:
    return ast.parse(HARNESS.read_text(encoding="utf-8"))


def _calls() -> set[str]:
    """Return every MCP tool name the harness calls.

    The harness routes every call through its own ``call_tool`` helper, whose
    signature is ``call_tool(session, name, arguments)``, so the tool name is
    the second positional argument.
    """
    names: set[str] = set()
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id == "call_tool":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                names.add(str(node.args[1].value))
        elif (isinstance(function, ast.Attribute)
                and function.attr == "call_tool"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)):
            names.add(str(node.args[1].value))
    return names


def _source() -> str:
    return HARNESS.read_text(encoding="utf-8")


class GameSideHarnessSafetyTests(unittest.TestCase):
    def test_the_harness_never_writes_to_the_source_save(self):
        """The source save is opened read-only and only copied."""
        source = _source()
        self.assertIn("shutil.copy2(MODDED_SAVE, run_save)", source)
        for forbidden in (
            "MODDED_SAVE.write_bytes", 'MODDED_SAVE.open("w")',
            "MODDED_SAVE.open('w')", "shutil.copy2(run_save, MODDED_SAVE)",
            "shutil.move(run_save, MODDED_SAVE)",
        ):
            self.assertNotIn(forbidden, source)

    def test_the_source_save_digest_is_compared_before_and_after(self):
        source = _source()
        self.assertIn("save_digest_before", source)
        self.assertIn("save_digest_after", source)
        self.assertIn("save_unchanged", source)

    def test_the_harness_uses_only_the_restricted_backend_tools(self):
        """No arbitrary Lua and no tool outside the restricted boundary."""
        names = _calls()
        self.assertTrue(names)
        for name in names:
            self.assertTrue(
                name.startswith("autoengineer_"),
                f"{name} is not a restricted backend tool",
            )
        self.assertIn("autoengineer_operation", names)
        self.assertIn("autoengineer_operation_preview", names)
        self.assertIn("autoengineer_arm", names)
        self.assertIn("autoengineer_stop", names)

    def test_the_harness_never_executes_raw_lua_over_rcon(self):
        """Arbitrary Lua would bypass the restricted boundary."""
        source = _source()
        for forbidden in (
            "ExecuteLuaAsync", "rcon.print", "--command", "execute-console",
        ):
            self.assertNotIn(forbidden, source)

    def test_the_craft_cases_stay_inside_the_backend_allowlist(self):
        """Every crafted item must be one the backend itself permits."""
        operation = OPERATION.read_text(encoding="utf-8")
        allowed_line = operation.split('kind == "craft" && new[]')[1]
        allowed = set(re.findall(r'"([a-z-]+)"', allowed_line.split(")")[0]))
        self.assertTrue(allowed)
        source = _source()
        for case in ("iron-gear-wheel", "copper-cable"):
            self.assertIn(case, source)
            self.assertIn(case, allowed)

    def test_the_lease_is_released_even_when_a_craft_fails(self):
        source = _source()
        self.assertIn("finally:", source)
        self.assertIn("autoengineer_stop", source)

    def test_the_rcon_password_belongs_to_the_environment(self):
        """A reused server was started with the password of that time.

        A per-run password would make a reused server unreachable with
        "RCON authentication failed", so the secret is environment-scoped.
        """
        source = _source()
        self.assertIn("env.rcon_password()", source)
        self.assertIn("rcon_secret_is_environment_scoped", source)

    def test_the_rcon_secret_is_never_written_into_the_report(self):
        source = _source()
        self.assertNotIn("report[\"rcon_password\"]", source)
        self.assertNotIn("'rcon_password': password", source)

    def test_the_harness_only_stops_the_processes_it_started(self):
        source = _source()
        self.assertIn("for process in (client, proc):", source)
        # It must not kill every factorio process on the machine.
        self.assertNotIn("taskkill", source)
        self.assertNotIn("Stop-Process", source)

    def test_the_harness_reads_the_catalog_before_planning(self):
        source = _source()
        self.assertIn("catalogPage", source)
        self.assertIn("catalog_rows", source)


class JoinDetectionTests(unittest.TestCase):
    """The join must be detected from the server's own multiplayer lines.

    Factorio writes the join as a timestamped chat line, so a harness that
    looks for a "Player ... joined" pattern never matches it and a
    successful join is reported as a failure.
    """

    def test_the_join_line_of_the_observed_server_log_is_detected(self):
        import live_r06_game_side_verify as harness

        # The exact line the Factorio 2.1.23 server wrote in the observed run.
        line = "2026-10-25 07:56:42 [JOIN] lawfulrocky joined the game"
        self.assertTrue(harness.join_evidence(line))

    def test_a_refusal_is_not_a_join(self):
        import live_r06_game_side_verify as harness

        refusal = ("  51.744 Refusing connection for address "
                   "(IP ADDR:({127.0.0.1:56829})), username (). "
                   "UserVerificationMissing")
        self.assertFalse(harness.join_evidence(refusal))

    def test_the_multiplayer_state_lines_are_also_detected(self):
        import live_r06_game_side_verify as harness

        for line in (
            "74.041 Info ServerMultiplayerManager.cpp:977: updateTick(1075) "
            "received stateChanged peerID(1) oldState(Ready) "
            "newState(ConnectedWaitingForMap)",
            "74.090 Info ServerMultiplayerManager.cpp:1038: UpdateTick(1075) "
            "Serving map(...mp-save-0.zip) for peer(1)",
            "74.591 Info ServerMultiplayerManager.cpp:977: updateTick(1077) "
            "received stateChanged peerID(1) oldState"
            "(WaitingForCommandToStartSendingTickClosures) newState(InGame)",
        ):
            self.assertTrue(harness.join_evidence(line), line)

    def test_the_join_window_is_long_enough_for_the_mod_load(self):
        """The client loads twenty mods before it connects."""
        import live_r06_game_side_verify as harness

        self.assertGreaterEqual(harness.JOIN_WINDOW_SECONDS, 600)


class PersistentEnvironmentTests(unittest.TestCase):
    """The harness must use one persistent, reusable test environment.

    These tests pin the defect that made the previous harness ask the user to
    sign in again on every run: it created a **fresh, empty client profile
    per run**, so the client's ``player-data.json`` had an empty
    ``service-token`` and the headless client could never complete the
    authentication handshake against ``auth.factorio.com``.
    """

    def test_the_harness_uses_the_persistent_environment_module(self):
        import live_r06_game_side_verify as harness

        self.assertTrue(hasattr(harness, "env"))
        self.assertTrue(hasattr(harness.env, "prepare_client_profile"))

    def test_the_client_profile_is_persistent_not_created_per_run(self):
        """A per-run client directory loses the authentication state."""
        import r06_live_environment as environment

        client_profile = str(environment.CLIENT_PROFILE)
        self.assertNotIn("{", client_profile)
        self.assertNotIn("run_tag", client_profile)
        self.assertIn("client-profile", client_profile)

    def test_the_client_profile_is_never_deleted_by_the_harness(self):
        """Deleting the profile would discard the token again."""
        source = _source()
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("rmtree(", source)

    def test_the_harness_seeds_the_client_profile_before_launching(self):
        """The profile must be seeded before the client process is started."""
        tree = _tree()
        main_fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        calls: list[tuple[int, str]] = []
        for node in ast.walk(main_fn):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if isinstance(function, ast.Name):
                calls.append((node.lineno, function.id))
            elif isinstance(function, ast.Attribute):
                calls.append((node.lineno, function.attr))
        seed_lines = [line for line, name in calls
                      if name == "prepare_client_profile"]
        start_lines = [line for line, name in calls
                       if name in ("start_server", "start_client", "Popen")]
        self.assertTrue(seed_lines, "main() must seed the client profile")
        self.assertTrue(start_lines, "main() must start the server or client")
        self.assertLess(min(seed_lines), min(start_lines))

    def test_the_harness_checks_the_client_authentication_state(self):
        """An unauthenticated profile must fail fast, not hang."""
        source = _source()
        self.assertIn("has_authentication", source)
        self.assertIn("client_auth_state", source)

    def test_an_existing_server_is_reused_instead_of_relaunched(self):
        source = _source()
        self.assertIn("discover_running_server", source)
        self.assertIn("server_reused", source)

    def test_a_reused_server_is_left_running(self):
        """Only the processes this harness started may be stopped."""
        source = _source()
        self.assertIn("server_left_running", source)
        self.assertIn("for process in (client, proc):", source)

    def test_the_server_readiness_wait_is_bounded(self):
        import live_r06_game_side_verify as harness

        self.assertLessEqual(harness.SERVER_READY_SECONDS, 900)
        self.assertGreater(harness.SERVER_READY_SECONDS, 0)


class AuthenticationDiagnosticsTests(unittest.TestCase):
    """The harness must say where the handshake stopped."""

    def test_a_refusal_is_reported_as_refusal_evidence(self):
        import live_r06_game_side_verify as harness

        refusal = ("  51.744 Refusing connection for address "
                   "(IP ADDR:({127.0.0.1:56829})), username (). "
                   "UserVerificationMissing")
        self.assertTrue(harness.refusal_evidence(refusal))

    def test_a_successful_handshake_reports_every_stage(self):
        import live_r06_game_side_verify as harness

        client_log = (
            "  57.644 Info AuthServerConnector.cpp:620: Performing TLS check.\n"
            "  58.042 Info HttpSharedState.cpp:57: Downloading "
            "https://auth.factorio.com/api-login?api_version=6\n"
            "  60.064 Info AuthServerConnector.cpp:204: Got token from auth "
            "server for username(lawfulrocky).\n"
            "  60.066 Info HttpSharedState.cpp:57: Downloading "
            "https://auth.factorio.com/generate-user-server-key-2?api_version=6\n"
            "  60.387 Info AuthServerConnector.cpp:149: Received key from "
            "auth server.\n"
            "  60.416 Info ClientMultiplayerManager.cpp:610: changing state "
            "from(Connecting) to(ConnectedWaitingForMap)\n"
        )
        progress = harness.auth_progress(client_log)
        self.assertTrue(progress["login_requested"])
        self.assertTrue(progress["token_received"])
        self.assertEqual(progress["last_stage"], "reconnect")

    def test_a_stalled_handshake_is_distinguished_from_a_slow_one(self):
        """The failing run reached TLS check but never issued api-login."""
        import live_r06_game_side_verify as harness

        stalled = (
            " 543.208 Info AuthServerConnector.cpp:620: Performing TLS check.\n"
            " 543.577 Info AuthServerConnector.cpp:653: TLS check success.\n"
        )
        progress = harness.auth_progress(stalled)
        self.assertFalse(progress["login_requested"])
        self.assertFalse(progress["token_received"])
        self.assertEqual(progress["last_stage"], "tls_check")

    def test_an_empty_client_log_reports_no_stage(self):
        import live_r06_game_side_verify as harness

        progress = harness.auth_progress("")
        self.assertIsNone(progress["last_stage"])
        self.assertFalse(progress["login_requested"])


class PlayerReadyWaitTests(unittest.TestCase):
    """The harness must wait for a real player, not for a guessed interval.

    The client's join is detected on the server's multiplayer state lines,
    which happen before the client has downloaded the map and spawned its
    character. The backend's observation gate needs exactly one connected
    player with a character, so a fixed sleep after the join is a race. The
    observed live run lost it: the view answered "unavailable" because the
    character had not spawned yet.
    """

    def test_the_player_ready_wait_is_bounded(self):
        import live_r06_game_side_verify as harness

        self.assertGreater(harness.PLAYER_READY_SECONDS, 0)
        self.assertLessEqual(harness.PLAYER_READY_SECONDS, 600)

    def test_the_harness_polls_the_view_instead_of_sleeping(self):
        source = _source()
        self.assertIn("wait_for_player_ready", source)
        self.assertIn("autoengineer_view", source)
        # The fixed post-join sleep must be gone.
        self.assertNotIn("time.sleep(8)", source)

    def test_the_readiness_signal_is_the_player_observation(self):
        """The catalog's metadata is not a readiness signal.

        The adapter reports the catalog's identity even when the
        player-dependent part of the observation is still empty, so the
        readiness check must look at the player's own force and surface,
        which are reported inside the capability payload.
        """
        source = _source()
        self.assertIn("player_ready_force", source)
        self.assertIn("player_ready_surface", source)
        self.assertIn("observed_identity(payload)", source)

    def test_the_wait_gives_up_with_a_reason(self):
        import live_r06_game_side_verify as harness

        source = _source()
        self.assertIn("player_ready_reason", source)
        self.assertTrue(hasattr(harness, "wait_for_player_ready"))


class CapabilityPayloadTests(unittest.TestCase):
    """The observed recipe rows live in the capability payload.

    The restricted backend reports the observation under ``capabilities``. The
    recipe rows of a catalog page are ``capabilities.recipes``; they are not
    at the top level. A payload without a player carries only ``status``.
    """

    def test_the_recipe_rows_are_read_from_the_capability_payload(self):
        import live_r06_game_side_verify as harness

        payload = {"status": "ok", "capabilities": {"recipes": [
            {"name": "iron-gear-wheel"}, {"name": "copper-cable"}]}}
        rows = harness.capability_rows(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "iron-gear-wheel")

    def test_a_payload_without_capabilities_has_no_recipe_rows(self):
        import live_r06_game_side_verify as harness

        self.assertEqual(harness.capability_rows({"status": "unavailable"}), [])
        self.assertEqual(harness.capability_rows({}), [])

    def test_a_capability_payload_without_recipes_has_no_recipe_rows(self):
        import live_r06_game_side_verify as harness

        self.assertEqual(
            harness.capability_rows({"capabilities": {"schema": 1}}), [])

    def test_the_observed_identity_comes_from_the_capability_payload(self):
        import live_r06_game_side_verify as harness

        payload = {"capabilities": {"force": "player", "surface": "nauvis"}}
        self.assertEqual(harness.observed_identity(payload),
                         ("player", "nauvis"))

    def test_a_payload_without_an_identity_reports_none(self):
        import live_r06_game_side_verify as harness

        self.assertEqual(harness.observed_identity({"status": "ok"}),
                         (None, None))

    def test_the_harness_reads_the_recipes_from_the_capability_payload(self):
        source = _source()
        self.assertIn("capability_rows(payload)", source)


class BackendModeTests(unittest.TestCase):
    """The read-only AI Helper mode must stay the default.

    The restricted backend refuses lease activation and every gameplay write
    in the AI Helper mode ("AI Helper denies gameplay writes and lease
    activation"). The harness therefore defaults to that mode and skips the
    in-game craft with an explicit reason instead of attempting it.
    """

    def test_the_default_mode_is_the_read_only_helper_mode(self):
        self.assertIn("--backend-mode", _source())
        self.assertIn('default="helper"', _source())

    def test_only_the_known_modes_are_accepted(self):
        import r06_live_environment as environment

        self.assertEqual(set(environment.BACKEND_MODES), {"helper", "semi"})

    def test_an_unknown_mode_is_refused(self):
        import r06_live_environment as environment

        with self.assertRaises(ValueError):
            environment.backend_launch_environment(27161, "x", "full")

    def test_the_helper_mode_is_the_read_only_default(self):
        import r06_live_environment as environment

        environment_default = environment.backend_launch_environment(27161, "x")
        self.assertEqual(environment_default["AUTOENGINEER_BACKEND_MODE"],
                         "helper")

    def test_the_supervised_mode_is_selectable(self):
        import r06_live_environment as environment

        supervised = environment.backend_launch_environment(27161, "x", "semi")
        self.assertEqual(supervised["AUTOENGINEER_BACKEND_MODE"], "semi")

    def test_the_craft_is_skipped_in_the_helper_mode(self):
        source = _source()
        self.assertIn("game_side_skipped_mode", source)
        self.assertIn("read-only", source)

    def test_the_helper_mode_never_arms_a_lease(self):
        """The read-only mode must not attempt a lease at all."""
        source = _source()
        self.assertIn("if mode != \"semi\":", source)


class PreflightTests(unittest.TestCase):
    """The preflight must report a blocking problem before any process starts."""

    def test_a_missing_backend_is_reported(self):
        import live_r06_game_side_verify as harness

        problems = harness.preflight(
            Path("does-not-exist.dll"), harness.EXE, harness.MODS,
            harness.MODDED_SAVE,
        )
        self.assertTrue(problems)
        self.assertTrue(any("backend" in problem for problem in problems))

    def test_a_missing_save_is_reported(self):
        import live_r06_game_side_verify as harness

        problems = harness.preflight(
            harness.RESTRICTED_BACKEND, harness.EXE, harness.MODS,
            Path("does-not-exist.zip"),
        )
        self.assertTrue(problems)
        self.assertTrue(any("save" in problem for problem in problems))

    def test_the_real_prerequisites_pass_the_preflight(self):
        import live_r06_game_side_verify as harness

        problems = harness.preflight(
            harness.RESTRICTED_BACKEND, harness.EXE, harness.MODS,
            harness.MODDED_SAVE,
        )
        self.assertEqual(problems, [])

    def test_the_harness_runs_the_preflight_before_starting_a_process(self):
        source = _source()
        self.assertIn("PREFLIGHT=PASS", source)
        self.assertIn("problems = preflight(", source)
        # The preflight must run before any process is started. The process
        # start may live in a helper, so the invariant is asserted on the
        # call order inside main() rather than on raw source offsets.
        tree = _tree()
        main_fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        calls: list[tuple[int, str]] = []
        for node in ast.walk(main_fn):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if isinstance(function, ast.Name):
                calls.append((node.lineno, function.id))
            elif isinstance(function, ast.Attribute):
                calls.append((node.lineno, function.attr))
        preflight_lines = [line for line, name in calls if name == "preflight"]
        start_lines = [line for line, name in calls
                       if name in ("start_server", "start_client", "Popen")]
        self.assertTrue(preflight_lines, "main() must call the preflight")
        self.assertTrue(start_lines, "main() must start the server or client")
        self.assertLess(min(preflight_lines), min(start_lines))

    def test_the_harness_never_starts_a_process_outside_main(self):
        """Only main() may launch Factorio, so the preflight always runs."""
        tree = _tree()
        launchers = {
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "Popen"
                for inner in ast.walk(node)
            )
        }
        self.assertTrue(launchers)
        self.assertNotIn("main", launchers)


if __name__ == "__main__":
    unittest.main()
