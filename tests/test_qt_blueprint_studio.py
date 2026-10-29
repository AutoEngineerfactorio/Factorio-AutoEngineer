"""Functional Qt Blueprint Studio regression tests, using the R07 codec."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    QApplication = import_module("PySide6.QtWidgets").QApplication
    from blueprint_encoder import encode_document
    from qt_blueprint_studio import BlueprintStudio
    from qt_shell import ShellWindow
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


def simple_blueprint(count=3):
    return {"blueprint": {"version": 562949954076672,
                          "label": "Verified Fixture",
                          "entities": [{"entity_number": n + 1,
                                        "name": "transport-belt",
                                        "position": {"x": n, "y": -n},
                                        "direction": 2}
                                       for n in range(count)]}}


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class BlueprintStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = BlueprintStudio()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def test_studio_has_library_designer_and_preview_tabs(self):
        self.assertEqual(self.widget.tabs.count(), 3)
        self.assertEqual(self.widget.tabs.tabText(0), "My Library & Books")
        self.assertEqual(self.widget.tabs.tabText(1), "Create Blueprint")
        self.assertEqual(self.widget.tabs.tabText(2), "Preview & Export")
        self.assertIsNotNone(self.widget.designer)
        self.assertIsNotNone(self.widget.library_panel)

    def test_saving_a_valid_document_uses_local_library(self):
        from blueprint_library_store import BlueprintLibraryStore

        with tempfile.TemporaryDirectory() as temporary:
            self.widget.library_panel.store = BlueprintLibraryStore(Path(temporary))
            self.assertTrue(self.widget.load_exchange(
                encode_document(simple_blueprint())))
            self.widget.save_to_library()
            self.assertEqual(len(self.widget.library_panel.store.entries), 1)
            self.assertIn("local", self.widget.status.text().lower())

    def test_empty_state_has_no_export_action(self):
        self.assertFalse(self.widget.copy_button.isEnabled())
        self.assertFalse(self.widget.save_button.isEnabled())
        self.assertEqual(self.widget.entities.rowCount(), 0)

    def test_valid_import_shows_entities_and_round_trips(self):
        source = simple_blueprint()
        exchange = encode_document(source)
        self.assertTrue(self.widget.load_exchange(exchange))
        self.assertEqual(self.widget.document, source)
        self.assertEqual(self.widget.entities.rowCount(), 3)
        self.assertEqual(len(self.widget.scene.items()), 3)
        self.assertIn("VALIDATED", self.widget.status.text())
        self.assertTrue(self.widget.save_button.isEnabled())

    def test_copy_export_is_a_real_clipboard_action(self):
        exchange = encode_document(simple_blueprint())
        self.assertTrue(self.widget.load_exchange(exchange))
        self.widget.copy_exchange()
        self.assertEqual(QApplication.clipboard().text(), self.widget.export_text)

    def test_invalid_import_refuses_and_clears_prior_preview(self):
        self.assertTrue(self.widget.load_exchange(encode_document(simple_blueprint())))
        self.assertFalse(self.widget.load_exchange("0not-base64"))
        self.assertIsNone(self.widget.document)
        self.assertFalse(self.widget.copy_button.isEnabled())
        self.assertEqual(self.widget.entities.rowCount(), 0)
        self.assertEqual(len(self.widget.scene.items()), 0)
        self.assertIn("refused", self.widget.status.text())

    def test_import_from_file_and_saved_export(self):
        exchange = encode_document(simple_blueprint(5))
        with tempfile.TemporaryDirectory() as d:
            inp = Path(d) / "input.txt"
            output = Path(d) / "export.txt"
            inp.write_text(exchange + "\n", encoding="utf-8")
            self.assertTrue(self.widget.load_path(inp))
            self.assertEqual(self.widget.entities.rowCount(), 5)
            with patch("qt_blueprint_studio.qtw.QFileDialog.getSaveFileName",
                       return_value=(str(output), "Text files (*.txt)")):
                self.widget.save_file()
            self.assertEqual(output.read_text(encoding="utf-8").strip(),
                             self.widget.export_text)

    def test_book_import_displays_entities_from_nested_books(self):
        blueprint = simple_blueprint(2)["blueprint"]
        book = {"blueprint_book": {
            "version": 562949954076672,
            "blueprints": [
                {"index": 1, "blueprint": blueprint},
                {"index": 2, "blueprint_book": {
                    "version": 562949954076672,
                    "blueprints": [{"index": 4, "blueprint": blueprint}],
                }},
            ],
        }}
        self.assertTrue(self.widget.load_exchange(encode_document(book)))
        self.assertEqual(self.widget.entities.rowCount(), 4)
        self.assertIn("book entries", self.widget.summary.text())
        self.assertEqual(self.widget.entities.item(2, 4).text(), "/2/4")

    def test_drawing_and_table_are_bounded(self):
        self.assertTrue(self.widget.load_exchange(
            encode_document(simple_blueprint(920))))
        self.assertEqual(self.widget.entities.rowCount(), 500)
        self.assertLessEqual(len(self.widget.scene.items()), 750)
        self.assertIn("920 entities", self.widget.details.text())

    def test_clear_refuses_export_and_drops_rows(self):
        self.assertTrue(self.widget.load_exchange(
            encode_document(simple_blueprint())))
        self.widget.clear()
        self.assertEqual(self.widget.entities.rowCount(), 0)
        self.assertFalse(self.widget.save_button.isEnabled())
        self.assertIsNone(self.widget.document)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class BlueprintShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_studio_is_integrated_into_real_shell(self):
        shell = ShellWindow()
        try:
            shell.show_workspace("Blueprint Studio")
            studio = shell.blueprint_widget()
            self.assertEqual(shell.current_workspace, "Blueprint Studio")
            self.assertIsInstance(studio, BlueprintStudio)
            self.assertTrue(studio.load_exchange(
                encode_document(simple_blueprint())))
            self.assertEqual(studio.entities.rowCount(), 3)
        finally:
            shell.close()
            shell.deleteLater()


if __name__ == "__main__":
    unittest.main()
