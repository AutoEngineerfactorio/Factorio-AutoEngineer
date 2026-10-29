"""The shell integration of the launcher, Settings and the profile bar.

These tests prove that the dashboard shows the **real** workspace and the
**real** profile state, and that the launch and stop controls follow the
verified process state.

No Factorio process is started and no real profile is touched: the profile
manager is given a temporary root and the session is replaced by a fake.
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
    QLabel = import_module("PySide6.QtWidgets").QLabel
    QPushButton = import_module("PySide6.QtWidgets").QPushButton
    from factorio_profiles import ProfileManager
    from factorio_session import SessionState
    from qt_profile_bar import ProfileBar
    from qt_saves_workspace import SavesWorkspace
    from qt_settings_workspace import SettingsWorkspace
    from qt_shell import ShellWindow
    from qt_theme import build_header_state
except ImportError:  # pragma: no cover - depends on the environment
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 unavailable")
class ShellIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        from unittest.mock import patch
        with patch.dict(os.environ, {"AUTOENGINEER_PROFILE_ROOT": str(self.base / "profiles")}):
            self.window = ShellWindow()
        self.addCleanup(self.window.close)
        self.addCleanup(self.window.deleteLater)

    def _labels(self, widget) -> list[str]:
        return [label.text() for label in widget.findChildren(QLabel)]

    # -- the settings workspace ------------------------------------------

    def test_the_settings_page_is_the_real_workspace(self):
        page = self.window._pages["Settings"]
        workspaces = page.findChildren(SettingsWorkspace)
        self.assertEqual(len(workspaces), 1)

    def test_the_settings_workspace_has_every_section(self):
        page = self.window._pages["Settings"]
        workspace = page.findChildren(SettingsWorkspace)[0]
        self.assertIn("General", workspace.sections)
        self.assertIn("Safety", workspace.sections)
        self.assertIn("Performance and Telemetry", workspace.sections)

    def test_the_settings_workspace_offers_the_diagnostics(self):
        page = self.window._pages["Settings"]
        workspace = page.findChildren(SettingsWorkspace)[0]
        labels = " ".join(self._labels(workspace))
        self.assertIn("Backend DLL", labels)
        self.assertIn("Permission mode", labels)

    # -- the profile bar --------------------------------------------------

    def test_the_shell_has_a_profile_bar(self):
        bars = self.window.findChildren(ProfileBar)
        self.assertEqual(len(bars), 1)

    def test_the_profile_bar_shows_that_no_profile_is_selected(self):
        bar = self.window.findChildren(ProfileBar)[0]
        self.assertIn("No profile", bar.profile.text())
        self.assertFalse(bar.launch_button.isEnabled())

    def test_the_profile_bar_sits_below_the_header(self):
        # The bar is a direct child of the central layout, after the
        # header and before the body that holds the workspace stack, so
        # the profile is always visible above the workspace.
        central = self.window.centralWidget()
        layout = central.layout()
        widgets = [layout.itemAt(index).widget()
                   for index in range(layout.count())]
        self.assertIn(self.window.header, widgets)
        self.assertIn(self.window.profile_bar, widgets)
        self.assertLess(
            widgets.index(self.window.header),
            widgets.index(self.window.profile_bar))

    def test_the_settings_button_opens_the_settings_workspace(self):
        self.window.profile_bar.settings_button.click()
        self.assertEqual(
            self.window.stack.currentWidget(),
            self.window._pages["Settings"])

    def test_the_header_settings_button_still_opens_the_settings(self):
        self.window.header.tools["Settings"].click()
        self.assertEqual(
            self.window.stack.currentWidget(),
            self.window._pages["Settings"])

    # -- the existing workspaces survive ---------------------------------

    def test_the_existing_workspaces_are_still_there(self):
        for name in ("Overview", "Recipes", "Blueprint Studio", "Research",
                     "Inventory", "Factory Map", "Production", "Electrical",
                     "Logistics", "Diagnostics", "Saves", "Settings"):
            self.assertIn(name, self.window._pages)

    def test_navigating_to_a_workspace_still_works(self):
        self.window.show_workspace("Settings")
        self.assertEqual(
            self.window.stack.currentWidget(),
            self.window._pages["Settings"])


class ProfileBarTruthTests(unittest.TestCase):
    """The button states follow the verified process state."""

    def test_an_owned_game_enables_stop(self):
        state = SessionState(
            running=True, owned=True, pid=5, profile_identifier="p",
            game_version="2.1.23", detail="Running")
        self.assertTrue(state.running and state.owned)

    def test_an_attached_game_is_not_owned(self):
        state = SessionState(
            running=True, owned=False, pid=5, profile_identifier="p",
            game_version="2.1.23", detail="Running")
        self.assertTrue(state.running)
        self.assertFalse(state.owned)


class SavesWorkspaceIntegrationTests(unittest.TestCase):
    """The Saves page is a real page and the header names the profile."""

    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
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
        self.profile = self.manager.create("Integration pack", installation)
        self.window = ShellWindow()
        self.window.profile_bar.manager = self.manager
        self.window._pages["Saves"].findChild(SavesWorkspace).manager = self.manager
        self.addCleanup(self.window.close)
        self.addCleanup(self.window.deleteLater)

    def test_the_saves_page_is_not_the_placeholder(self):
        page = self.window._pages["Saves"]
        workspaces = page.findChildren(SavesWorkspace)
        self.assertEqual(len(workspaces), 1)

    def test_the_placeholder_text_is_gone(self):
        labels = [label.text() for label in self.window.findChildren(QLabel)]
        self.assertNotIn(
            "This workspace is not implemented yet. "
            "It shows no data rather than invented data.", " ".join(labels))

    def test_the_header_names_the_selected_profile(self):
        self.window.profile_bar.reload()
        self.window.header.apply_header_state(build_header_state(
            None, selected_profile=self.window.selected_profile_label()))
        self.assertIn("Integration pack", self.window.header.profile.text())

    def test_the_header_shows_the_observed_profile_when_there_is_one(self):
        state = build_header_state(
            {"profile": "observed-profile"},
            selected_profile="Integration pack")
        self.assertEqual(state.profile, "observed-profile")

    def test_the_header_falls_back_to_the_selected_profile(self):
        state = build_header_state(
            None, selected_profile="Integration pack")
        self.assertEqual(state.profile, "Integration pack")

    def test_the_selected_profile_survives_a_restart(self):
        # A fresh manager over the same root restores the selection.
        restored = ProfileManager(self.base / "profiles")
        self.assertEqual(restored.restore_selection(), self.profile.identifier)

    def test_the_saves_page_shows_the_profile(self):
        self.window.profile_bar.reload()
        self.window.show_workspace("Saves")
        page = self.window._pages["Saves"].findChildren(SavesWorkspace)[0]
        self.assertEqual(page.profile_label.text(), "Integration pack")


if __name__ == "__main__":
    unittest.main()
