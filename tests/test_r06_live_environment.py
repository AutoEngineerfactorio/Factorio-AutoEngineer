"""Regression tests for the persistent R06 live test environment.

The defect these tests pin is the one that made the previous R06 live
harness ask the user to sign in again on every run: the harness created a
**fresh, empty client profile per run**, so the client's ``player-data.json``
had an empty ``service-token`` and the headless client could never complete
the authentication handshake against ``auth.factorio.com``.

These tests are offline and never launch Factorio. They exercise the real
functions of ``tests/r06_live_environment.py`` against temporary directories.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import r06_live_environment as env  # noqa: E402

BASE_CONFIG = """[path]
read-data=D:/read-data
write-data=D:/write-data

[other]
local-rcon-socket=127.0.0.1:27109
local-rcon-password=original-secret
enable-blueprint-storage-cloud-sync=false
"""


def _write_player_data(path: Path, token: str = "", username: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "service-token": token,
        "service-username": username,
        "last-played": {"nested": {"value": 1}},
        "tips": [1, 2, 3],
    }), encoding="utf-8")
    return path


class DefaultSaveTests(unittest.TestCase):
    def test_pyanodons_default_is_separate_from_vanilla(self):
        self.assertEqual(env.MODDED_SAVE.parent, env.LAUNCHER_PROFILE / "data" / "saves")
        self.assertEqual(env.MODDED_SAVE.name, "autoengineer-py-fresh-20261028.zip")


class AuthStateTests(unittest.TestCase):
    """The authentication state must be reported without leaking the token."""

    def test_an_empty_token_is_reported_as_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_player_data(Path(tmp) / "player-data.json")
            state = env.read_auth_state(path)
            self.assertEqual(state["service-token"], "absent")

    def test_a_present_token_is_reported_by_length_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_player_data(Path(tmp) / "player-data.json",
                                      token="t" * 30, username="someone")
            state = env.read_auth_state(path)
            self.assertEqual(state["service-token"], "present:30")
            self.assertEqual(state["service-username"], "present:7")
            # The token value must never appear in the reported state.
            self.assertNotIn("t" * 30, json.dumps(state))

    def test_a_missing_profile_has_no_authentication(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            self.assertFalse(env.has_authentication(path))
            self.assertEqual(env.read_auth_state(path), {})

    def test_an_unreadable_profile_is_not_claimed_to_be_authenticated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "player-data.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertFalse(env.has_authentication(path))


class SeedingTests(unittest.TestCase):
    """The client profile must be seeded from the authenticated profile."""

    def test_seeding_copies_only_the_authentication_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _write_player_data(Path(tmp) / "source.json",
                                        token="t" * 30, username="someone")
            target = Path(tmp) / "target" / "player-data.json"
            state = env.seed_authentication(source, target)
            self.assertEqual(state["service-token"], "present:30")
            seeded = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(sorted(seeded), ["service-token", "service-username"])
            # No unrelated player state may leak into the client profile.
            self.assertNotIn("last-played", seeded)
            self.assertNotIn("tips", seeded)

    def test_seeding_an_untokenised_source_fails_with_a_clear_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _write_player_data(Path(tmp) / "source.json")
            target = Path(tmp) / "target.json"
            with self.assertRaises(env.EnvironmentError_) as caught:
                env.seed_authentication(source, target)
            self.assertIn("sign in once", str(caught.exception))
            # The target must not be created when the source is unusable.
            self.assertFalse(target.exists())

    def test_an_existing_client_token_is_kept_not_overwritten(self):
        """The persistent profile's own token is the one the game refreshes."""
        with tempfile.TemporaryDirectory() as tmp:
            source = _write_player_data(Path(tmp) / "source.json",
                                        token="s" * 30, username="sourceuser")
            target = _write_player_data(Path(tmp) / "target.json",
                                        token="c" * 30, username="clientuser")
            state = env.seed_authentication(source, target)
            self.assertEqual(state["service-token"], "present:30")
            self.assertEqual(state["service-username"], "present:10")
            seeded = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(seeded["service-username"], "clientuser")

    def test_a_fresh_target_gets_the_source_token(self):
        """This is the exact defect: an empty target is never left empty."""
        with tempfile.TemporaryDirectory() as tmp:
            source = _write_player_data(Path(tmp) / "source.json",
                                        token="s" * 30, username="sourceuser")
            target = Path(tmp) / "nested" / "target.json"
            env.seed_authentication(source, target)
            self.assertTrue(env.has_authentication(target))


class ClientConfigTests(unittest.TestCase):
    """The client needs its own write-data and the run's RCON port."""

    def test_the_client_gets_its_own_write_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.ini"
            base.write_text(BASE_CONFIG, encoding="utf-8")
            data_dir = Path(tmp) / "client" / "data"
            config = env.write_client_config(
                Path(tmp) / "client.ini", base, data_dir, 27161)
            text = config.read_text(encoding="utf-8")
            self.assertIn("write-data=" + str(data_dir).replace("\\", "/"), text)
            self.assertTrue(data_dir.is_dir())

    def test_the_rcon_socket_is_bound_to_localhost(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.ini"
            base.write_text(BASE_CONFIG, encoding="utf-8")
            config = env.write_client_config(
                Path(tmp) / "client.ini", base, Path(tmp) / "data", 27161)
            text = config.read_text(encoding="utf-8")
            self.assertIn("local-rcon-socket=127.0.0.1:27161", text)
            self.assertNotIn("0.0.0.0", text)

    def test_a_config_without_the_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.ini"
            base.write_text("[path]\nwrite-data=D:/x\n", encoding="utf-8")
            with self.assertRaises(env.EnvironmentError_):
                env.write_client_config(
                    Path(tmp) / "client.ini", base, Path(tmp) / "data", 27161)


class BoundedWaitTests(unittest.TestCase):
    """Every wait must be bounded and must report why it ended."""

    def test_a_condition_that_becomes_true_succeeds(self):
        calls = {"n": 0}

        def predicate():
            calls["n"] += 1
            return calls["n"] >= 3

        result = env.wait_for(predicate, timeout=5.0,
                              description="the server became ready")
        self.assertTrue(result.ok)
        self.assertEqual(result.reason, "the server became ready")
        self.assertGreaterEqual(calls["n"], 3)

    def test_a_timeout_is_reported_with_the_duration(self):
        result = env.wait_for(lambda: None, timeout=0.3,
                              description="the client joined")
        self.assertFalse(result.ok)
        self.assertIn("the client joined", result.reason)
        self.assertIn("did not happen within", result.reason)

    def test_an_impossible_condition_stops_immediately_with_its_reason(self):
        def predicate():
            return "the client has no authentication token"

        result = env.wait_for(predicate, timeout=30.0,
                              description="the client joined")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "the client has no authentication token")
        self.assertLess(result.waited_seconds, 5.0)

    def test_an_exception_in_the_predicate_is_reported(self):
        def predicate():
            raise ValueError("boom")

        result = env.wait_for(predicate, timeout=5.0, description="the check")
        self.assertFalse(result.ok)
        self.assertIn("ValueError", result.reason)


class ServerReuseTests(unittest.TestCase):
    """An already-running server must be detected and reused."""

    def test_a_closed_port_is_not_a_healthy_server(self):
        self.assertFalse(env.server_is_healthy(1, host="127.0.0.1"))

    def test_discovery_uses_the_rcon_health_check(self):
        checked: list[int] = []

        def fake(port: int, host: str = "127.0.0.1") -> bool:
            checked.append(port)
            return True

        original = env.rcon_is_listening
        env.rcon_is_listening = fake  # type: ignore[assignment]
        try:
            self.assertTrue(env.discover_running_server(27161))
        finally:
            env.rcon_is_listening = original  # type: ignore[assignment]
        self.assertEqual(checked, [27161])

    def test_rcon_is_always_bound_to_localhost(self):
        self.assertEqual(env.RCON_HOST, "127.0.0.1")


class PersistentProfileTests(unittest.TestCase):
    """The persistent client profile is reused, not recreated per run."""

    def test_the_client_profile_is_not_inside_the_evidence_directory(self):
        """A per-run directory would lose the authentication state."""
        self.assertNotIn(str(env.EVIDENCE), str(env.CLIENT_PROFILE))
        self.assertIn("client-profile", str(env.CLIENT_PROFILE))

    def test_the_persistent_profile_is_shared_by_every_run(self):
        """The path does not depend on the run tag."""
        self.assertNotIn("{", str(env.CLIENT_PROFILE))
        self.assertNotIn("run_tag", str(env.CLIENT_PROFILE))

    def test_the_modded_save_is_never_the_profile_directory(self):
        self.assertNotEqual(env.MODDED_SAVE, env.CLIENT_PROFILE)


class BackendLaunchEnvironmentTests(unittest.TestCase):
    """The restricted backend must be hosted from a resolvable .NET root.

    The live run failed with "Could not load file or assembly 'System.Runtime,
    Version=9.0.0.0'" because ``DOTNET_ROOT`` is not set in this environment
    and the harness launched the assembly without resolving the shared
    framework.
    """

    def test_the_dotnet_root_is_derived_from_the_executable(self):
        root = env.dotnet_root()
        self.assertTrue(root, "the .NET root could not be derived")
        self.assertTrue(Path(root).is_dir())
        self.assertTrue((Path(root) / "dotnet.exe").is_file())

    def test_the_backend_environment_carries_the_dotnet_root(self):
        environment = env.backend_launch_environment(27161, "secret")
        self.assertIn("DOTNET_ROOT", environment)
        self.assertTrue(environment["DOTNET_ROOT"])

    def test_the_backend_environment_carries_the_rcon_settings(self):
        environment = env.backend_launch_environment(27161, "secret")
        self.assertEqual(environment["FACTORIO_RCON_HOST"], "127.0.0.1")
        self.assertEqual(environment["FACTORIO_RCON_PORT"], "27161")
        self.assertEqual(environment["FACTORIO_RCON_PASSWORD"], "secret")
        self.assertEqual(environment["AUTOENGINEER_BACKEND_MODE"], "helper")

    def test_the_backend_state_files_stay_outside_the_repository_root(self):
        environment = env.backend_launch_environment(27161, "secret")
        for key in ("FACTORIO_GOALS_FILE", "FACTORIO_BUILDINGS_FILE"):
            self.assertTrue(environment[key].startswith(str(env.BASE)))

    def test_the_backend_runtime_directory_is_created(self):
        env.backend_launch_environment(27161, "secret")
        self.assertTrue(env.BACKEND_RUNTIME.is_dir())


class ProfileLockTests(unittest.TestCase):
    """A stale lock stops the client from starting at all.

    Factorio refuses to start when its profile's ``.lock`` file exists. The
    lock is only meaningful while the game runs, so a lock left behind by a
    previous run prevents the next client from starting. The observed live
    run produced an empty client log and no handshake at all because of it.
    """

    def test_a_stale_lock_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            (data / ".lock").write_bytes(b"")
            self.assertTrue(env.clear_stale_lock(data))
            self.assertFalse((data / ".lock").exists())

    def test_removing_a_missing_lock_reports_nothing_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            self.assertFalse(env.clear_stale_lock(data))

    def test_the_lock_is_removed_from_the_persistent_client_profile(self):
        data = env.CLIENT_PROFILE / "data"
        lock = data / ".lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_bytes(b"")
        env.prepare_client_profile("lock-test", env.BASE / "server" / "config.ini")
        self.assertFalse(lock.exists())


class ProfileGameLogTests(unittest.TestCase):
    """The game's log is written into the profile, not to standard output."""

    def test_the_log_path_is_inside_the_profile(self):
        path = env.game_log_path(Path("/tmp/profile/data"))
        self.assertEqual(path.name, "factorio-current.log")
        self.assertIn("data", str(path))

    def test_the_log_is_read_from_the_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            (data / "factorio-current.log").write_text(
                "JOIN happened here", encoding="utf-8")
            self.assertIn("JOIN happened", env.read_game_log(data))

    def test_a_missing_log_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(env.read_game_log(Path(tmp)), "")


class RconSecretTests(unittest.TestCase):
    """The RCON password belongs to the environment, not to a run.

    A reused server was started with the password that was current then. A
    per-run password makes the reused server unreachable with "RCON
    authentication failed", which is exactly what the observed live run
    showed.
    """

    def test_the_password_is_stable_between_calls(self):
        original = env.BASE
        with tempfile.TemporaryDirectory() as tmp:
            env.BASE = Path(tmp)  # type: ignore[misc]
            try:
                first = env.rcon_password()
                second = env.rcon_password()
                self.assertEqual(first, second)
                self.assertTrue(first)
            finally:
                env.BASE = original  # type: ignore[misc]

    def test_the_secret_is_stored_in_the_environment(self):
        original = env.BASE
        with tempfile.TemporaryDirectory() as tmp:
            env.BASE = Path(tmp)  # type: ignore[misc]
            try:
                password = env.rcon_password()
                self.assertTrue(env.rcon_secret_path().is_file())
                stored = json.loads(
                    env.rcon_secret_path().read_text(encoding="utf-8"))
                self.assertEqual(stored["rcon_password"], password)
            finally:
                env.BASE = original  # type: ignore[misc]

    def test_a_corrupt_secret_is_replaced(self):
        original = env.BASE
        with tempfile.TemporaryDirectory() as tmp:
            env.BASE = Path(tmp)  # type: ignore[misc]
            try:
                env.rcon_secret_path().parent.mkdir(parents=True, exist_ok=True)
                env.rcon_secret_path().write_text("{not json", encoding="utf-8")
                password = env.rcon_password()
                self.assertTrue(password)
            finally:
                env.BASE = original  # type: ignore[misc]

    def test_the_password_is_not_the_empty_string(self):
        original = env.BASE
        with tempfile.TemporaryDirectory() as tmp:
            env.BASE = Path(tmp)  # type: ignore[misc]
            try:
                self.assertNotEqual(env.rcon_password(), "")
            finally:
                env.BASE = original  # type: ignore[misc]


class DisposableSaveTests(unittest.TestCase):
    """The source save must only ever be copied."""

    def test_the_copy_is_a_separate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.zip"
            source.write_bytes(b"payload")
            copy = env.copy_disposable_save(
                source, "run-tag", destination=Path(tmp) / "out" / "run.zip")
            self.assertNotEqual(copy, source)
            self.assertEqual(copy.read_bytes(), b"payload")
            self.assertEqual(source.read_bytes(), b"payload")

    def test_the_source_save_is_copied_never_moved(self):
        """The disposable copy must not be the source path itself."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.zip"
            source.write_bytes(b"payload")
            copy = env.copy_disposable_save(
                source, "run-tag", destination=Path(tmp) / "run.zip")
            self.assertNotEqual(copy.resolve(), source.resolve())
            self.assertTrue(copy.is_file())
            # The source still exists after the copy: nothing was moved.
            self.assertTrue(source.is_file())

    def test_the_copy_lands_in_the_evidence_directory_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.zip"
            source.write_bytes(b"payload")
            copy = env.copy_disposable_save(source, "run-tag")
            self.assertEqual(copy.parent, env.EVIDENCE)
            copy.unlink()

    def test_the_real_modded_save_is_the_expected_isolated_file(self):
        """The environment must point at the isolated disposable save."""
        self.assertTrue(env.MODDED_SAVE.name.endswith(".zip"))
        self.assertIn("launcher-profiles", str(env.MODDED_SAVE))
        # It is inside the repository's own isolated profile tree, never in
        # the user's own Factorio installation directory.
        self.assertTrue(str(env.MODDED_SAVE).startswith(str(ROOT)))


class PersistentCatalogHarnessTests(unittest.TestCase):
    """Catalog sweep and legacy runner must not trigger reauthentication."""

    def test_both_catalog_runners_reuse_authenticated_client(self):
        for name in ("r06_live_catalog_sweep.py", "live_modded_catalog_verify.py"):
            with self.subTest(runner=name):
                source = (ROOT / "tests" / name).read_text(encoding="utf-8")
                self.assertIn("env.prepare_client_profile(", source)
                self.assertIn("env.has_authentication(", source)
                self.assertIn('"--mod-directory", str(MODS)', source)
                self.assertNotIn('client_root = EVIDENCE / f"', source)

    def test_old_catalog_runner_never_deletes_persistent_client(self):
        source = (ROOT / "tests" / "live_modded_catalog_verify.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"client_profile_preserved"', source)
        self.assertNotIn("shutil.rmtree(client_root", source)


if __name__ == "__main__":
    unittest.main()
