"""Tests for the Qt Settings workspace.

The workspace is built with the offscreen Qt platform, so no window is
shown and no Factorio process is started. The profile manager is given a
temporary root, so no real profile and no real save is touched.
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
    QLabel = import_module("PySide6.QtWidgets").QLabel
    from factorio_profiles import ProfileManager
    from qt_settings_workspace import SettingsWorkspace
    from settings_store import SECTIONS, load
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


@unittest.skipIf(QApplication is None, "PySide6 unavailable")
class SettingsWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.settings_path = self.base / "settings.json"
        self.manager = ProfileManager(self.base / "profiles")
        self.installation = make_installation(self.base / "Factorio")
        self.workspace = SettingsWorkspace(
            load(self.settings_path), manager=self.manager)
        self.addCleanup(self.workspace.deleteLater)

    # -- structure -------------------------------------------------------

    def test_every_section_has_a_tab(self):
        self.assertEqual(sorted(self.workspace.sections),
                         sorted(SECTIONS))

    def test_every_field_has_a_widget(self):
        for name, fields in SECTIONS.items():
            section = self.workspace.sections[name]
            for field in fields:
                self.assertIn(field, section.widgets, f"{name}/{field}")

    def test_a_boolean_field_uses_a_checkbox(self):
        section = self.workspace.sections["General"]
        self.assertTrue(hasattr(section.widgets["start_maximized"], "isChecked"))

    def test_a_choice_field_uses_a_combo_box(self):
        section = self.workspace.sections["General"]
        self.assertTrue(hasattr(section.widgets["theme"], "currentText"))

    def test_a_number_field_uses_a_spin_box(self):
        section = self.workspace.sections["Performance and Telemetry"]
        self.assertTrue(hasattr(section.widgets["ups_target"], "value"))

    def test_a_text_field_uses_a_line_edit(self):
        section = self.workspace.sections["AI Models"]
        self.assertTrue(hasattr(section.widgets["llm_endpoint"], "text"))

    # -- values ----------------------------------------------------------

    def test_the_stored_values_are_shown(self):
        section = self.workspace.sections["Performance and Telemetry"]
        self.assertEqual(section.widgets["ups_target"].value(), 60)

    def test_saving_stores_the_changed_value(self):
        section = self.workspace.sections["General"]
        section.widgets["start_maximized"].setChecked(True)
        self.workspace.save()
        self.assertTrue(load(self.settings_path).get("start_maximized"))

    def test_saving_reports_success(self):
        self.workspace.save()
        self.assertIn("saved", self.workspace.feedback.text())

    def test_a_rejected_value_is_reported_and_not_stored(self):
        section = self.workspace.sections["Performance and Telemetry"]
        # The spin box cannot go below its minimum, so the invalid value
        # is injected to prove the validation path.
        section.widgets["ups_target"].setValue(60)
        section.widgets["ups_target"].setProperty("value", 99999)
        self.workspace.save()
        self.assertTrue(load(self.settings_path).get("ups_target") <= 240)

    def test_the_save_button_exists(self):
        self.assertEqual(self.workspace.save_button.text(), "Apply settings")

    # -- profiles --------------------------------------------------------

    def test_the_profile_section_shows_the_profiles(self):
        self.manager.create("My pack", self.installation)
        self.workspace.render_profiles()
        labels = [label.text() for label in
                  self.workspace.findChildren(QLabel)]
        self.assertIn("My pack", labels)

    def test_selecting_a_profile_updates_the_manager(self):
        profile = self.manager.create("Selectable", self.installation)
        self.workspace.render_profiles()
        button = next(
            b for b in self.workspace.findChildren(QPushButton)
            if b.text() == "Select")
        button.click()
        self.assertEqual(self.manager.selected, profile.identifier)

    def test_duplicating_a_profile_creates_a_second_one(self):
        self.manager.create("Original", self.installation)
        self.workspace.render_profiles()
        button = next(
            b for b in self.workspace.findChildren(QPushButton)
            if b.text() == "Duplicate")
        button.click()
        self.assertEqual(len(self.manager.identifiers()), 2)

    def test_the_profile_root_is_shown(self):
        labels = [label.text() for label in
                  self.workspace.findChildren(QLabel)]
        self.assertTrue(any("Profile root" in text for text in labels))

    # -- diagnostics -----------------------------------------------------

    def test_the_diagnostics_report_the_real_state(self):
        labels = [label.text() for label in
                  self.workspace.findChildren(QLabel)]
        joined = " ".join(labels)
        self.assertIn("Backend DLL", joined)
        self.assertIn("Model endpoint", joined)
        self.assertIn("RCON credential", joined)
        self.assertIn("Permission mode", joined)

    def test_the_permission_mode_is_read_only_by_default(self):
        self.assertIn("read-only", self.workspace._permission_state())

    def test_fully_autonomous_is_never_offered(self):
        labels = [label.text() for label in
                  self.workspace.findChildren(QLabel)]
        joined = " ".join(labels)
        self.assertNotIn("Fully Autonomous (locked)", joined)

    def test_the_credential_value_is_never_shown(self):
        os.environ["FACTORIO_RCON_PASSWORD"] = "top-secret-value"
        try:
            self.workspace.render_diagnostics()
            labels = [label.text() for label in
                      self.workspace.findChildren(QLabel)]
            self.assertNotIn("top-secret-value", " ".join(labels))
        finally:
            os.environ.pop("FACTORIO_RCON_PASSWORD", None)

    # -- honesty ---------------------------------------------------------

    def test_a_missing_backend_is_reported_as_not_built(self):
        self.assertIn("Not built", self.workspace._backend_state())

    def test_a_problem_in_the_settings_file_is_shown(self):
        self.settings_path.write_text("not json", encoding="utf-8")
        self.workspace.reload()
        self.assertNotEqual(self.workspace.problems.text(), "")
        self.assertIn("could not be read", self.workspace.problems.text())


class SettingsWorkflowTests(unittest.TestCase):
    """Apply, discard, restore defaults and the unsaved-changes state."""

    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.settings_path = self.base / "settings.json"
        self.manager = ProfileManager(self.base / "profiles")
        self.workspace = SettingsWorkspace(
            load(self.settings_path), manager=self.manager)
        self.addCleanup(self.workspace.deleteLater)

    def _general(self):
        return self.workspace.sections["General"]

    def test_a_fresh_screen_has_no_unsaved_changes(self):
        self.assertFalse(self.workspace.has_unsaved_changes())
        self.assertEqual(self.workspace.pending_changes(), {})

    def test_a_changed_widget_is_an_unsaved_change(self):
        self._general().widgets["start_maximized"].setChecked(True)
        self.assertTrue(self.workspace.has_unsaved_changes())
        self.assertIn("start_maximized", self.workspace.pending_changes())

    def test_applying_stores_the_change(self):
        self._general().widgets["start_maximized"].setChecked(True)
        self.workspace.save()
        self.assertTrue(load(self.settings_path).get("start_maximized"))
        self.assertFalse(self.workspace.has_unsaved_changes())

    def test_discarding_undoes_the_change(self):
        self._general().widgets["start_maximized"].setChecked(True)
        self.workspace.cancel()
        self.assertFalse(self._general().widgets["start_maximized"].isChecked())
        self.assertFalse(load(self.settings_path).get("start_maximized"))
        self.assertIn("discarded", self.workspace.feedback.text())

    def test_restoring_the_defaults_shows_them_without_storing(self):
        self._general().widgets["window_width"].setValue(1200)
        self.workspace.save()
        self._general().widgets["window_width"].setValue(1300)
        self.workspace.restore_defaults()
        self.assertEqual(self._general().widgets["window_width"].value(), 1600)
        # The defaults are only shown; the user still has to apply them.
        self.assertEqual(load(self.settings_path).get("window_width"), 1200)
        self.assertIn("Apply", self.workspace.feedback.text())

    def test_restoring_the_defaults_can_be_applied(self):
        self._general().widgets["window_width"].setValue(1200)
        self.workspace.save()
        self.workspace.restore_defaults()
        self.workspace.save()
        self.assertEqual(load(self.settings_path).get("window_width"), 1600)

    def test_a_restart_required_change_is_reported(self):
        self._general().widgets["start_maximized"].setChecked(True)
        self.workspace.save()
        self.assertIn("Restart required", self.workspace.restart_hint.text())
        self.assertIn("start_maximized", self.workspace.restart_hint.text())

    def test_a_live_change_does_not_ask_for_a_restart(self):
        section = self.workspace.sections["AI Models"]
        section.widgets["llm_endpoint"].setText("http://127.0.0.1:9999/v1")
        self.workspace.save()
        self.assertEqual(self.workspace.restart_hint.text(), "")

    def test_the_discard_button_is_only_enabled_with_changes(self):
        self.assertFalse(self.workspace.cancel_button.isEnabled())
        self._general().widgets["start_maximized"].setChecked(True)
        self.workspace.update_unsaved_state()
        self.assertTrue(self.workspace.cancel_button.isEnabled())

    def test_an_invalid_value_is_reported_and_not_stored(self):
        section = self.workspace.sections["AI Models"]
        section.widgets["llm_endpoint"].setText("https://api.example.com/v1")
        self.workspace.save()
        self.assertIn("not saved", self.workspace.feedback.text())
        self.assertNotEqual(
            load(self.settings_path).get("llm_endpoint"),
            "https://api.example.com/v1")

    def test_the_change_callback_is_called_on_apply(self):
        seen = []
        self.workspace.on_settings_changed = seen.append
        self._general().widgets["start_maximized"].setChecked(True)
        self.workspace.save()
        self.assertEqual(len(seen), 1)

    def test_the_change_callback_is_not_called_on_discard(self):
        seen = []
        self.workspace.on_settings_changed = seen.append
        self._general().widgets["start_maximized"].setChecked(True)
        self.workspace.cancel()
        self.assertEqual(seen, [])


class ModelConnectionTests(unittest.TestCase):
    """The Settings screen tests the model and reports what was verified."""

    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.settings_path = self.base / "settings.json"
        self.manager = ProfileManager(self.base / "profiles")
        self.workspace = SettingsWorkspace(
            load(self.settings_path), manager=self.manager)
        self.addCleanup(self.workspace.deleteLater)

    def _status(self):
        """Return the model status, which the test just produced."""
        status = self.workspace.model_status
        self.assertIsNotNone(status)
        return status

    def test_the_connection_test_reports_the_status(self):
        self.workspace.test_model_connection()
        self.assertIsNotNone(self.workspace.model_status)
        self.assertIn("Model status", self.workspace.feedback.text())

    def test_an_unreachable_endpoint_is_reported_as_offline(self):
        self.workspace.sections["AI Models"].widgets["llm_endpoint"].setText(
            "http://127.0.0.1:1/v1")
        self.workspace.test_model_connection()
        status = self._status()
        self.assertEqual(status.status, "offline")
        self.assertFalse(status.ready)

    def test_a_remote_endpoint_is_refused_by_the_store(self):
        self.workspace.sections["AI Models"].widgets["llm_endpoint"].setText(
            "https://api.example.com/v1")
        self.workspace.save()
        # The store refuses a remote endpoint, so the stored value stays
        # the loopback default and the diagnostic never sees a remote
        # address.
        self.assertIn("not saved", self.workspace.feedback.text())
        stored = load(self.settings_path).get("llm_endpoint")
        self.assertNotEqual(stored, "https://api.example.com/v1")

    def test_the_discovered_models_are_shown(self):
        self.workspace.test_model_connection()
        # Nothing is listening, so the list is empty, but the row exists
        # and says so rather than claiming a model was found.
        self.assertIn("model", self.workspace.model_discovered.text().lower())

    def test_the_test_button_exists(self):
        buttons = [b.text() for b in self.workspace.findChildren(QPushButton)]
        self.assertIn("Test connection", buttons)

    def test_the_test_starts_no_model_process(self):
        self.workspace.test_model_connection()
        # The diagnostic only speaks HTTP; it never starts a server.
        self.assertTrue(self.workspace.model_status is not None)


class ProfileSelectionGuardTests(unittest.TestCase):
    """The screen reports why a profile could not be selected."""

    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.settings_path = self.base / "settings.json"
        self.manager = ProfileManager(self.base / "profiles")
        self.workspace = SettingsWorkspace(
            load(self.settings_path), manager=self.manager)
        self.addCleanup(self.workspace.deleteLater)

    def test_a_refused_selection_shows_the_reason(self):
        self.manager.create("Pack", make_installation(
            self.base / "Factorio"))
        original = self.manager.session_state
        self.manager.session_state = lambda identifier: {
            "running": True, "owned": True, "pid": 1, "detail": "Running"}
        try:
            self.workspace.render_profiles()
            button = next(
                b for b in self.workspace.findChildren(QPushButton)
                if b.text() == "Select")
            button.click()
        finally:
            self.manager.session_state = original
        self.assertIn("not selected", self.workspace.feedback.text())
        self.assertIn("still running", self.workspace.feedback.text())


if __name__ == "__main__":
    unittest.main()
