"""Tests for the profile bar and the game controls.

No Factorio process is started: the session is replaced by a fake, so the
tests verify the decision logic and the button states.
"""
from __future__ import annotations

import os
import sys
import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    QApplication = import_module("PySide6.QtWidgets").QApplication
    QPushButton = import_module("PySide6.QtWidgets").QPushButton
    from factorio_profiles import ProfileManager
    from factorio_session import SessionError, SessionState
    from qt_profile_bar import ProfileBar
except ImportError:  # pragma: no cover - depends on the environment
    QApplication = None


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


class FakeSession:
    """A stand-in for the game session."""

    def __init__(self, profile, state: SessionState | None = None,
                 fail: str | None = None):
        self.profile = profile
        self.state_value = state or SessionState(
            running=False, owned=False, pid=None,
            profile_identifier=profile.identifier,
            game_version=profile.game_version, detail="Not running")
        self.fail = fail
        self.launched = False
        self.stopped = False

    def state(self) -> SessionState:
        return self.state_value

    def launch(self, *, confirm: bool = False) -> SessionState:
        if self.fail:
            raise SessionError(self.fail)
        self.launched = True
        self.state_value = SessionState(
            running=True, owned=True, pid=1,
            profile_identifier=self.profile.identifier,
            game_version=self.profile.game_version,
            detail="Running, started by AutoEngineer")
        return self.state_value

    def stop(self, *, confirm: bool = False) -> SessionState:
        if self.fail:
            raise SessionError(self.fail)
        self.stopped = True
        self.state_value = SessionState(
            running=False, owned=False, pid=None,
            profile_identifier=self.profile.identifier,
            game_version=self.profile.game_version, detail="Not running")
        return self.state_value


@unittest.skipIf(QApplication is None, "PySide6 unavailable")
class ProfileBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.manager = ProfileManager(self.base / "profiles")
        self.installation = make_installation(self.base / "Factorio")
        self.session: FakeSession | None = None
        self.answers: list[bool] = []
        self.bar = ProfileBar(
            self.manager,
            session_factory=self._session_factory,
            confirm=self._confirm)
        self.addCleanup(self.bar.deleteLater)

    def _session_factory(self, profile):
        self.session = FakeSession(profile)
        return self.session

    def _fake(self) -> FakeSession:
        """Return the fake session, which the tests always created."""
        assert self.session is not None
        return self.session

    def _confirm(self, question: str) -> bool:
        self.answers.append(True)
        return True

    def _refuse(self, question: str) -> bool:
        self.answers.append(False)
        return False

    # -- state -----------------------------------------------------------

    def test_without_a_profile_the_bar_says_so(self):
        self.assertIn("No profile", self.bar.profile.text())
        self.assertEqual(self.bar.version.text(), "—")

    def test_the_launch_button_is_disabled_without_a_profile(self):
        self.assertFalse(self.bar.launch_button.isEnabled())
        self.assertFalse(self.bar.stop_button.isEnabled())

    def test_a_selected_profile_is_shown_with_its_version(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self.assertEqual(self.bar.profile.text(), "My pack")
        self.assertIn("unknown", self.bar.version.text())

    def test_the_launch_button_is_enabled_for_a_selected_profile(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self.assertTrue(self.bar.launch_button.isEnabled())
        self.assertFalse(self.bar.stop_button.isEnabled())

    def test_an_owned_game_enables_stop_and_disables_launch(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self._fake().state_value = SessionState(
            running=True, owned=True, pid=7,
            profile_identifier=profile.identifier, game_version=None,
            detail="Running")
        self.bar.reload()
        self.assertFalse(self.bar.launch_button.isEnabled())
        self.assertTrue(self.bar.stop_button.isEnabled())
        self.assertIn("started by AutoEngineer", self.bar.state.text())

    def test_an_attached_game_keeps_stop_disabled(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self._fake().state_value = SessionState(
            running=True, owned=False, pid=9,
            profile_identifier=profile.identifier, game_version=None,
            detail="Running")
        self.bar.reload()
        self.assertFalse(self.bar.stop_button.isEnabled())
        self.assertFalse(self.bar.launch_button.isEnabled())
        self.assertIn("outside AutoEngineer", self.bar.state.text())

    # -- actions ---------------------------------------------------------

    def test_launching_asks_for_a_confirmation(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self.bar.confirm = self._refuse
        self.bar.launch()
        self.assertEqual(self.answers, [False])
        self.assertFalse(self._fake().launched)
        self.assertIn("not started", self.bar.feedback.text())

    def test_a_confirmed_launch_starts_the_game(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self.bar.launch()
        self.assertEqual(self.answers, [True])
        self.assertTrue(self._fake().launched)

    def test_a_refused_launch_does_not_start_the_game(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self.bar.confirm = self._refuse
        self.bar.launch()
        self.assertFalse(self._fake().launched)

    def test_a_failed_launch_is_reported(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self._fake().fail = "Another Factorio instance is already running"
        self.bar.launch()
        self.assertIn("not started", self.bar.feedback.text())
        self.assertIn("already running", self.bar.feedback.text())

    def test_stopping_asks_for_a_confirmation(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self._fake().state_value = SessionState(
            running=True, owned=True, pid=7,
            profile_identifier=profile.identifier, game_version=None,
            detail="Running")
        self.bar.reload()
        self.bar.confirm = self._refuse
        self.bar.stop()
        self.assertEqual(self.answers, [False])
        self.assertFalse(self._fake().stopped)
        self.assertIn("not stopped", self.bar.feedback.text())

    def test_a_confirmed_stop_stops_the_game(self):
        profile = self.manager.create("My pack", self.installation)
        self.manager.select(profile.identifier)
        self.bar.reload()
        self._fake().state_value = SessionState(
            running=True, owned=True, pid=7,
            profile_identifier=profile.identifier, game_version=None,
            detail="Running")
        self.bar.reload()
        self.bar.stop()
        self.assertTrue(self._fake().stopped)

    def test_an_unreadable_profile_is_reported(self):
        profile = self.manager.create("Gone", self.installation)
        self.manager.select(profile.identifier)
        self.manager.delete(profile.identifier, confirm=True)
        self.bar.reload()
        self.assertIn("unreadable", self.bar.profile.text())
        self.assertFalse(self.bar.launch_button.isEnabled())

    def test_the_settings_button_exists(self):
        buttons = [b.text() for b in self.bar.findChildren(QPushButton)]
        self.assertIn("Settings", buttons)


if __name__ == "__main__":
    unittest.main()
