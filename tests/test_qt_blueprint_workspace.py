"""Interactive Qt Blueprint Studio library and observed planning acceptance."""
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
    from qt_blueprint_workspace import BlueprintWorkspace
    from qt_catalog import catalog_snapshot
    from qt_shell import ShellWindow
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


RECIPE = {"name": "iron-gear-wheel", "enabled": True, "hidden": False,
          "category": "crafting", "crafting_time": 0.5,
          "ingredients": [{"name": "iron-plate", "amount": 2}],
          "products": [{"name": "iron-gear-wheel", "amount": 1}]}
MACHINE = {"name": "assembling-machine-2", "crafting_speed": 0.75,
           "crafting_categories": ["crafting"]}
DOCUMENT = {"blueprint": {"version": 562949954076672, "entities": [
    {"entity_number": 1, "name": "iron-chest",
     "position": {"x": 0, "y": 0}}]}}
FRAME = {"catalog_status": {"status": "assembled",
                             "total_count": 1, "page": 1, "total_pages": 1},
         "capabilities": {"recipes": [RECIPE], "machines": [MACHINE],
                          "research": [], "source_fingerprint": "catalog-observed",
                          "game_version": "2.1.23", "truncated": False}}


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class BlueprintWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = BlueprintWorkspace(library_home=Path(self.temp.name))

    def tearDown(self):
        self.workspace.close()
        self.workspace.deleteLater()
        self.temp.cleanup()

    def test_library_tree_and_persistence(self):
        fid = self.workspace.library.add_folder("Mining")
        self.workspace.library.add_document("Iron chest", DOCUMENT, fid)
        self.workspace.refresh_library()
        self.assertEqual(self.workspace.tree.topLevelItemCount(), 1)
        self.assertEqual(self.workspace.tree.topLevelItem(0).childCount(), 1)

    def test_book_entry_is_browsable_in_tree(self):
        book = self.workspace.library.new_book("Base Designs")
        self.workspace.library.append_to_book(book, DOCUMENT)
        self.workspace.refresh_library()
        tree = self.workspace.tree.topLevelItem(0)
        self.assertEqual(tree.childCount(), 1)
        self.workspace.tree.setCurrentItem(tree.child(0))
        self.assertEqual(self.workspace.studio.entities.rowCount(), 1)

    def test_blueprint_is_selectable_and_previews(self):
        self.workspace.library.add_document("One chest", DOCUMENT)
        self.workspace.refresh_library()
        self.workspace.tree.setCurrentItem(self.workspace.tree.topLevelItem(0))
        self.assertEqual(self.workspace.studio.document, DOCUMENT)

    def test_generator_requires_full_observed_catalog(self):
        self.workspace.rate.setValue(180)
        self.assertFalse(self.workspace.generate())
        self.assertIn("complete", self.workspace.message.text().lower())

    def test_catalog_bound_generator_creates_exchange(self):
        self.workspace.set_observed_catalog(catalog_snapshot(FRAME))
        self.workspace.prompt.setPlainText("Build 180 iron-gear-wheel per minute")
        self.assertTrue(self.workspace.generate())
        assert self.workspace.studio.document is not None
        self.assertEqual(
            len(self.workspace.studio.document["blueprint"]["entities"]), 2)
        self.assertIn("Machines: 2", self.workspace.plan.toPlainText())
        self.assertIn("draft", self.workspace.message.text().lower())

    def test_partial_catalog_is_not_treated_as_complete(self):
        incomplete = {"catalog_status": {"status": "partial",
                                           "total_count": 10146},
                      "capabilities": FRAME["capabilities"]}
        self.workspace.set_observed_catalog(catalog_snapshot(incomplete))
        self.assertFalse(self.workspace.generate())

    def test_truncated_assembled_catalog_cannot_generate(self):
        incomplete = {**FRAME, "capabilities": {**FRAME["capabilities"], "truncated": True}}
        self.workspace.set_observed_catalog(catalog_snapshot(incomplete))
        self.assertFalse(self.workspace.generate())
        self.assertIn("complete", self.workspace.message.text().lower())

    def test_book_entry_can_be_renamed_from_tree(self):
        book = self.workspace.library.new_book("Test book")
        self.workspace.library.append_to_book(book, DOCUMENT)
        self.workspace.refresh_library()
        child = self.workspace.tree.topLevelItem(0).child(0)
        self.workspace.tree.setCurrentItem(child)
        self.workspace.edit_selected_entry("rename", label="New label")
        self.assertEqual(
            self.workspace.library.book_entry(book, (0,))["blueprint"]["label"],
            "New label")

    def test_book_export_is_valid_nested_document(self):
        book = self.workspace.library.new_book("Production book")
        self.workspace.library.append_to_book(book, DOCUMENT)
        self.assertTrue(self.workspace.studio.load_exchange(
            encode_document(self.workspace.library.document(book))))
        self.assertEqual(self.workspace.studio.entities.rowCount(), 1)

    def test_workspace_has_all_key_controls(self):
        self.assertIsNotNone(self.workspace.studio.scene)
        self.assertIsNotNone(self.workspace.search)
        self.assertIsNotNone(self.workspace.tree)
        self.assertIsNotNone(self.workspace.generate_button)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class BlueprintShellIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shell_uses_same_catalog_for_generator(self):
        with tempfile.TemporaryDirectory() as temporary:
            from qt_blueprint_workspace import BlueprintWorkspace
            with patch("qt_blueprint_workspace.LIBRARY_HOME", Path(temporary)):
                shell = ShellWindow()
            try:
                self.assertIsInstance(shell.blueprint_workspace(), BlueprintWorkspace)
                shell.set_catalog(FRAME)
                shell.blueprint_workspace().rate.setValue(180)
                self.assertTrue(shell.blueprint_workspace().generate())
                document = shell.blueprint_widget().document
                assert document is not None
                self.assertEqual(
                    len(document["blueprint"]["entities"]), 2)
            finally:
                shell.close()
                shell.deleteLater()


if __name__ == "__main__":
    unittest.main()
