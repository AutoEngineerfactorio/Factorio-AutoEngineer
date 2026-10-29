"""Blueprint library UI: persistent hierarchy and Factorio books."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    QApplication = import_module("PySide6.QtWidgets").QApplication
    from blueprint_library_store import DEFAULT_VERSION
    from qt_blueprint_library_panel import BlueprintLibraryPanel, nested_document
    ENABLED = True
except ImportError:
    ENABLED = False


def bp():
    return {"blueprint": {
        "version": DEFAULT_VERSION, "label": "Test print",
        "entities": [{"entity_number": 1, "name": "transport-belt",
                      "position": {"x": 1, "y": 2}}]}}


@unittest.skipUnless(ENABLED, "PySide6 unavailable")
class LibraryPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.widget = BlueprintLibraryPanel(root=Path(self.tmp.name))

    def tearDown(self):
        self.widget.close()
        self.tmp.cleanup()

    def test_save_tree_and_open_signal(self):
        item_id = self.widget.store_document(bp())
        self.assertEqual(self.widget.tree.topLevelItemCount(), 1)
        folder = self.widget.tree.topLevelItem(0)
        entry = folder.child(0)
        self.assertEqual(entry.data(0, 0x0100), (item_id, ()))
        self.widget.tree.setCurrentItem(entry)
        messages = []
        self.widget.openDocument.connect(messages.append)
        self.widget.open_selected()
        self.assertEqual(messages, [bp()])

    def test_book_hierarchy_and_nested_selection(self):
        blueprint_id = self.widget.store_document(bp())
        book_id = self.widget.create_book("My Book")
        self.widget.store.add_to_book(book_id, blueprint_id)
        self.widget.refresh()
        books = []
        for i in range(self.widget.tree.topLevelItemCount()):
            group = self.widget.tree.topLevelItem(i)
            for j in range(group.childCount()):
                candidate = group.child(j)
                if candidate.data(0, 0x0100) == (book_id, ()):
                    books.append(candidate)
        self.assertEqual(len(books), 1)
        book = books[0]
        self.assertEqual(book.childCount(), 1)
        self.widget.tree.setCurrentItem(book.child(0))
        self.assertEqual(self.widget.selected_document(), bp())
        self.assertEqual(nested_document(self.widget.store.get(book_id), (0,)), bp())

    def test_copy_selected_really_sets_clipboard(self):
        ident = self.widget.store_document(bp())
        selected = self.widget.tree.topLevelItem(0).child(0)
        self.assertEqual(selected.data(0, 0x0100)[0], ident)
        self.widget.tree.setCurrentItem(selected)
        self.widget.copy_selected()
        self.assertTrue(QApplication.clipboard().text().startswith("0"))


if __name__ == "__main__":
    unittest.main()
