"""Tests for the Qt Save Manager workspace.

The tests use a temporary profile with synthetic saves and a substituted
session. No game is started and no real save is touched.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    QApplication = __import__("importlib").import_module(
        "PySide6.QtWidgets").QApplication
    from factorio_profiles import ProfileManager
    from factorio_session import SessionState
    from qt_saves_workspace import SavesWorkspace
except ImportError:  # pragma: no cover - depends on the environment
    QApplication = None


def write_save(path: Path, *, version="2.1.23", mods=("base",)):
    """Write a synthetic save archive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("level.dat", json.dumps({
            "version": version,
            "mod_list": [{"name": name} for name in mods],
            "playtime": 120.0,
        }))
    return path


class FakeSession:
    """A substituted game session."""

    def __init__(self, profile, running=False, owned=False):
        self.profile = profile
        self._running = running
        self._owned = owned

    def state(self):
        return SessionState(
            running=self._running, owned=self._owned, pid=1 if self._running else None,
            profile_identifier=self.profile.identifier,
            game_version=self.profile.game_version,
            detail="Running" if self._running else "Not running")


@unittest.skipIf(QApplication is None, "PySide6 unavailable")
class SavesWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.manager = ProfileManager(self.base / "profiles")
        installation = self.base / "Factorio"
        (installation / "bin" / "x64").mkdir(parents=True)
        (installation / "bin" / "x64" / "factorio.exe").write_bytes(b"MZ")
        (installation / "mods").mkdir(parents=True)
        (installation / "mods" / "mod-list.json").write_text(
            '{"mods": [{"name": "base", "enabled": true}]}', encoding="utf-8")
        self.profile = self.manager.create("Test pack", installation)
        self.running = False
        self.owned = False
        self.answers = []
        self.workspace = SavesWorkspace(
            self.manager,
            session_factory=lambda profile: FakeSession(
                profile, self.running, self.owned),
            confirm=self._confirm)
        self.addCleanup(self.workspace.deleteLater)

    def _confirm(self, question):
        self.answers.append(question)
        return True

    # -- listing ---------------------------------------------------------

    def test_the_page_is_not_a_placeholder(self):
        labels = [label.text() for label in self.workspace.findChildren(
            __import__("importlib").import_module(
                "PySide6.QtWidgets").QLabel)]
        self.assertNotIn(
            "This workspace is not implemented yet. "
            "It shows no data rather than invented data.", " ".join(labels))

    def test_the_real_saves_are_listed(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.workspace.reload()
        self.assertEqual(self.workspace.table.rowCount(), 1)
        self.assertEqual(self.workspace.table.item(0, 0).text(), "world.zip")

    def test_the_profile_is_shown(self):
        self.workspace.reload()
        self.assertEqual(self.workspace.profile_label.text(), "Test pack")

    def test_the_save_location_is_shown(self):
        self.workspace.reload()
        self.assertIn("saves", self.workspace.location_label.text())

    def test_the_search_filters_the_list(self):
        write_save(self.profile.saves_directory / "world.zip")
        write_save(self.profile.saves_directory / "other.zip")
        self.workspace.reload()
        self.workspace.search.setText("world")
        self.assertEqual(self.workspace.table.rowCount(), 1)

    def test_the_sort_order_is_applied(self):
        write_save(self.profile.saves_directory / "b.zip")
        write_save(self.profile.saves_directory / "a.zip")
        self.workspace.reload()
        self.workspace.sort.setCurrentText("Name")
        self.assertEqual(self.workspace.table.item(0, 0).text(), "a.zip")

    def test_a_broken_save_is_shown_with_its_problem(self):
        (self.profile.saves_directory / "broken.zip").write_bytes(b"junk")
        self.workspace.reload()
        self.assertEqual(self.workspace.table.rowCount(), 1)
        self.assertNotEqual(self.workspace.table.item(0, 5).text(), "Ready")

    # -- buttons ---------------------------------------------------------

    def test_the_save_buttons_are_disabled_without_a_game(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.workspace.reload()
        self.workspace.table.selectRow(0)
        self.workspace.on_selection_changed()
        self.assertFalse(self.workspace.save_button.isEnabled())

    def test_the_save_button_is_enabled_for_an_owned_game(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.running = True
        self.owned = True
        self.workspace.reload()
        self.workspace.table.selectRow(0)
        self.workspace.on_selection_changed()
        self.assertTrue(self.workspace.save_button.isEnabled())

    def test_the_save_button_is_disabled_for_a_foreign_game(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.running = True
        self.owned = False
        self.workspace.reload()
        self.workspace.table.selectRow(0)
        self.workspace.on_selection_changed()
        self.assertFalse(self.workspace.save_button.isEnabled())
        self.assertIn("AutoEngineer did not start", self.workspace.save_button.toolTip())

    def test_the_save_of_a_foreign_game_is_refused(self):
        self.running = True
        self.owned = False
        self.workspace.on_save()
        self.assertIn("AutoEngineer did not start", self.workspace.status.text())

    def test_the_new_game_button_is_disabled_while_the_game_runs(self):
        self.running = True
        self.owned = True
        self.workspace.reload()
        self.assertFalse(self.workspace.new_game_button.isEnabled())

    def test_the_new_game_button_is_enabled_when_the_game_is_stopped(self):
        self.workspace.reload()
        self.assertTrue(self.workspace.new_game_button.isEnabled())

    # -- operations ------------------------------------------------------

    def test_a_backup_is_written(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.workspace.reload()
        self.workspace.table.selectRow(0)
        self.workspace.on_selection_changed()
        self.workspace.on_backup()
        self.assertIn("Backed up", self.workspace.status.text())
        backups = list(
            (self.profile.saves_directory / "backups").glob("*.zip"))
        self.assertEqual(len(backups), 1)

    def test_a_delete_needs_a_confirmation(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.workspace.reload()
        self.workspace.table.selectRow(0)
        self.workspace.on_selection_changed()
        self.workspace.confirm = lambda question: False
        self.workspace.on_delete()
        self.assertTrue((self.profile.saves_directory / "world.zip").is_file())
        self.assertIn("not confirmed", self.workspace.status.text())

    def test_a_confirmed_delete_removes_the_save_and_keeps_a_backup(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.workspace.reload()
        self.workspace.table.selectRow(0)
        self.workspace.on_selection_changed()
        self.workspace.on_delete()
        self.assertFalse((self.profile.saves_directory / "world.zip").exists())
        backups = list(
            (self.profile.saves_directory / "backups").glob("*.zip"))
        self.assertEqual(len(backups), 1)

    def test_the_restore_button_needs_a_backup(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.workspace.reload()
        self.workspace.table.selectRow(0)
        self.workspace.on_selection_changed()
        self.assertFalse(self.workspace.restore_button.isEnabled())
        self.workspace.on_backup()
        self.assertTrue(self.workspace.restore_button.isEnabled())

    def test_an_operation_without_a_selection_is_refused(self):
        self.workspace.on_backup()
        self.assertIn("No save", self.workspace.status.text())

    def test_the_status_can_be_cleared(self):
        self.workspace.on_backup()
        self.workspace.clear_status()
        self.assertEqual(self.workspace.status.text(), "")

    def test_the_page_refreshes_on_demand(self):
        write_save(self.profile.saves_directory / "world.zip")
        self.workspace.reload()
        self.assertEqual(self.workspace.table.rowCount(), 1)
        self.workspace.refresh_button.click()
        self.assertEqual(self.workspace.table.rowCount(), 1)


if __name__ == "__main__":
    unittest.main()
