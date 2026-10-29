"""Tests for the universal Factorio session service.

No Factorio process is started in these tests. The process interaction is
replaced by a fake, so the decision logic — the confirmation, the
duplicate-instance guard, the ownership rule — is what is verified.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from factorio_profiles import ProfileManager  # noqa: E402
from factorio_session import GameSession, SessionError  # noqa: E402


def make_installation(root: Path) -> Path:
    """Build a fake Factorio installation on disk."""
    executable = root / "bin" / "x64" / "factorio.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"MZ fake factorio")
    mods = root / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    (mods / "mod-list.json").write_text(
        '{"mods": [{"name": "base", "enabled": true}]}', encoding="utf-8")
    return root


class FakeProcess:
    """A stand-in for a started process."""

    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.terminated = False
        self._exit_code: int | None = None

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self) -> None:
        self.terminated = True
        self._exit_code = 0

    def wait(self, timeout: float | None = None) -> int:
        return self._exit_code if self._exit_code is not None else 0


class SessionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.installation = make_installation(self.base / "Factorio")
        self.manager = ProfileManager(self.base / "profiles")
        self.profile = self.manager.create("Test", self.installation)
        self.session = GameSession(self.profile)
        # The tests never touch a real process: the running-instance
        # lookup and the started process are both replaced.
        self.session.running_instances = lambda: []  # type: ignore[method-assign]
        self.started: list[list[str]] = []

    def fake_popen(self, arguments, **kwargs):
        self.started.append(list(arguments))
        process = FakeProcess()
        self.session.process = process
        return process

    def install_fake_popen(self, monkeypatch_target):
        import subprocess

        original = subprocess.Popen
        monkeypatch_target.Popen = self.fake_popen  # type: ignore[misc]
        self.addCleanup(setattr, monkeypatch_target, "Popen", original)


class SessionStateTests(SessionTestCase):
    def test_a_fresh_session_is_not_running(self):
        state = self.session.state()
        self.assertFalse(state.running)
        self.assertFalse(state.owned)
        self.assertIsNone(state.pid)

    def test_an_attached_instance_is_reported_as_not_owned(self):
        self.session.running_instances = lambda: [1234]  # type: ignore[method-assign]
        state = self.session.state()
        self.assertTrue(state.running)
        self.assertFalse(state.owned)
        self.assertIn("outside AutoEngineer", state.detail)

    def test_an_owned_instance_is_reported_as_owned(self):
        self.session.process = FakeProcess()
        state = self.session.state()
        self.assertTrue(state.running)
        self.assertTrue(state.owned)
        self.assertEqual(state.pid, 4242)


class SessionLaunchTests(SessionTestCase):
    def test_launching_without_confirmation_is_refused(self):
        with self.assertRaises(SessionError):
            self.session.launch()

    def test_a_second_instance_is_refused(self):
        self.session.running_instances = lambda: [999]  # type: ignore[method-assign]
        with self.assertRaisesRegex(SessionError, "already running"):
            self.session.launch(confirm=True)

    def test_launching_twice_is_refused(self):
        import subprocess

        self.install_fake_popen(subprocess)
        self.session.wait_until_running = lambda *args, **kwargs: True  # type: ignore[method-assign]
        self.session.launch(confirm=True)
        with self.assertRaisesRegex(SessionError, "already running"):
            self.session.launch(confirm=True)

    def test_a_missing_executable_is_refused(self):
        import subprocess

        self.install_fake_popen(subprocess)
        self.profile.executable.unlink()
        with self.assertRaisesRegex(SessionError, "executable"):
            self.session.launch(confirm=True)

    def test_a_failed_start_reports_the_problem(self):
        import subprocess

        self.install_fake_popen(subprocess)
        self.session.wait_until_running = lambda *args, **kwargs: False  # type: ignore[method-assign]
        with self.assertRaisesRegex(SessionError, "did not report itself"):
            self.session.launch(confirm=True)

    def test_a_successful_start_reports_running(self):
        import subprocess

        self.install_fake_popen(subprocess)
        self.session.wait_until_running = lambda *args, **kwargs: True  # type: ignore[method-assign]
        state = self.session.launch(confirm=True)
        self.assertTrue(state.running)
        self.assertTrue(state.owned)


class SessionStopTests(SessionTestCase):
    def test_stopping_without_confirmation_is_refused(self):
        with self.assertRaises(SessionError):
            self.session.stop()

    def test_an_attached_instance_is_never_stopped(self):
        self.session.running_instances = lambda: [4321]  # type: ignore[method-assign]
        with self.assertRaisesRegex(SessionError, "not started by"):
            self.session.stop(confirm=True)

    def test_stopping_a_running_game_stops_the_owned_process(self):
        self.session.process = FakeProcess()
        self.session.request_save = lambda: True  # type: ignore[method-assign]
        state = self.session.stop(confirm=True)
        self.assertFalse(state.running)
        self.assertTrue(self.session.process.terminated)

    def test_stopping_a_game_that_is_not_running_is_refused(self):
        with self.assertRaisesRegex(SessionError, "not running"):
            self.session.stop(confirm=True)

    def test_stopping_asks_for_a_save_first(self):
        self.session.process = FakeProcess()
        asked: list[bool] = []
        self.session.request_save = lambda: asked.append(True) or True  # type: ignore[method-assign]
        self.session.stop(confirm=True, save=True)
        self.assertEqual(asked, [True])


class RegisteredCommandTests(SessionTestCase):
    def test_an_unregistered_command_is_refused(self):
        with self.assertRaisesRegex(SessionError, "registered"):
            self.session.send_registered_command("/c game.player.print('x')")

    def test_without_a_password_no_command_is_sent(self):
        import os

        previous = os.environ.pop("FACTORIO_RCON_PASSWORD", None)
        self.addCleanup(
            os.environ.__setitem__, "FACTORIO_RCON_PASSWORD", previous
        ) if previous else None
        self.assertIsNone(self.session.send_registered_command("/autoengineer-status"))


class SessionCommandTests(SessionTestCase):
    def test_the_command_uses_the_profiles_own_config(self):
        arguments = self.session.command()
        self.assertEqual(arguments[0], str(self.profile.executable))
        self.assertIn("--config", arguments)
        config = Path(arguments[arguments.index("--config") + 1])
        self.assertEqual(config, self.profile.config_directory / "config.ini")

    def test_the_config_is_written_when_it_is_missing(self):
        self.assertFalse(
            (self.profile.config_directory / "config.ini").is_file())
        self.session.command()
        self.assertTrue(
            (self.profile.config_directory / "config.ini").is_file())

    def test_the_written_config_points_at_the_profiles_own_data(self):
        self.session.command()
        text = (self.profile.config_directory / "config.ini").read_text(
            encoding="utf-8")
        self.assertIn(f"write-data={self.profile.root}", text)

    def test_the_installation_is_never_written_to(self):
        before = sorted(str(item) for item in self.installation.rglob("*"))
        self.session.command()
        after = sorted(str(item) for item in self.installation.rglob("*"))
        self.assertEqual(before, after)

    def test_two_profiles_get_different_configurations(self):
        other = self.manager.create("Other", self.installation)
        from factorio_session import GameSession

        other_session = GameSession(other)
        first = self.session.command()[2]
        second = other_session.command()[2]
        self.assertNotEqual(first, second)


class SessionSaveTests(SessionTestCase):
    def test_the_saves_of_the_profile_are_listed(self):
        (self.profile.saves_directory / "world.zip").write_bytes(b"save")
        report = self.session.save_report()
        self.assertEqual(report["save_count"], 1)
        self.assertEqual(report["saves"], ["world.zip"])

    def test_another_profiles_saves_are_not_visible(self):
        other = self.manager.create("Other", self.installation)
        (other.saves_directory / "other.zip").write_bytes(b"save")
        report = self.session.save_report()
        self.assertEqual(report["save_count"], 0)


if __name__ == "__main__":
    unittest.main()
