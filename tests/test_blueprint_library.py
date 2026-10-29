"""Local persistence, nested-book fidelity, and safe library edits."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from blueprint_library import BlueprintLibrary, LibraryError

DOC = {"blueprint": {
    "version": 562949954076672, "item": "blueprint", "label": "Original",
    "entities": [{"entity_number": 1, "name": "iron-chest",
                  "position": {"x": 0, "y": 0}}],
}}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lib = BlueprintLibrary(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_folders_persist_across_restarts(self):
        folder = self.lib.add_folder("Factories")
        item = self.lib.add_document("Iron", DOC, parent=folder)
        next_library = BlueprintLibrary(self.root)
        self.assertEqual(next_library.children(folder)[0]["id"], item)
        self.assertEqual(next_library.document(item), DOC)

    def test_move_rename_and_no_folder_cycles(self):
        first = self.lib.add_folder("F1")
        second = self.lib.add_folder("F2", first)
        item = self.lib.add_document("Test", DOC, first)
        self.lib.rename(item, "Renamed")
        self.lib.move(item, second)
        self.assertEqual(self.lib.children(second)[0]["name"], "Renamed")
        with self.assertRaises(LibraryError):
            self.lib.move(first, second)

    def test_book_nested_book_and_round_trip(self):
        parent = self.lib.new_book("Production")
        child = self.lib.new_book("Nested")
        self.assertEqual(self.lib.append_to_book(parent, DOC), 0)
        self.assertEqual(self.lib.append_to_book(parent, self.lib.document(child)), 1)
        imported = self.lib.document(parent)
        self.assertEqual(len(imported["blueprint_book"]["blueprints"]), 2)
        self.assertEqual(imported["blueprint_book"]["blueprints"][1]["index"], 1)

    def test_folder_delete_refuses_nonempty(self):
        folder = self.lib.add_folder("Important")
        item = self.lib.add_document("BP", DOC, folder)
        with self.assertRaises(LibraryError):
            self.lib.delete(folder)
        self.lib.delete(item)
        self.lib.delete(folder)
        self.assertEqual(self.lib.children(), [])

    def test_input_validation_and_unsupported_doc(self):
        for name in ("", "x" * 97, "bad/path", "bad\nname"):
            with self.subTest(name=name), self.assertRaises(LibraryError):
                self.lib.add_folder(name)
        with self.assertRaises(ValueError):
            self.lib.add_document("Invalid", {"something": {}}, None)

    def test_edit_nested_book_entries_preserves_parent_and_order(self):
        root = self.lib.new_book("Factory book")
        inner = self.lib.new_book("Inside")
        self.lib.append_to_book(inner, DOC)
        self.lib.append_to_book(root, self.lib.document(inner))
        self.lib.append_to_book(root, DOC)
        self.lib.edit_book_entry(root, (0, 0), "rename", label="Improved iron chest")
        self.assertEqual(
            self.lib.book_entry(root, (0, 0))["blueprint"]["label"],
            "Improved iron chest")
        self.lib.edit_book_entry(root, (1,), "up")
        self.assertEqual(self.lib.book_entry(root, (0,)), DOC)
        self.lib.edit_book_entry(root, (0,), "remove")
        self.assertEqual(len(self.lib.document(root)["blueprint_book"]["blueprints"]), 1)

    def test_empty_book_selection_and_invalid_operation_refused(self):
        book = self.lib.new_book("Empty")
        with self.assertRaises(LibraryError):
            self.lib.book_entry(book, (0,))
        self.lib.append_to_book(book, DOC)
        with self.assertRaises(LibraryError):
            self.lib.edit_book_entry(book, (0,), "unknown")
        with self.assertRaises(LibraryError):
            self.lib.edit_book_entry(book, (0,), "down")

    def test_import_then_export_remains_faithful(self):
        from blueprint_encoder import encode_document
        uid = self.lib.import_exchange("Import", encode_document(DOC))
        self.assertEqual(self.lib.document(uid), DOC)

    def test_refuses_cross_folder_moves(self):
        item = self.lib.add_document("Mine", DOC)
        with self.assertRaises(LibraryError):
            self.lib.move(item, "not-a-real-folder")

    def test_disk_index_remains_valid_after_reload(self):
        self.lib.new_book("Sample")
        saved = BlueprintLibrary(self.root)
        self.assertEqual(len(saved.records), 1)
        self.assertTrue((self.root / "index.json").is_file())


if __name__ == "__main__":
    unittest.main()
