"""Persistent blueprint library and book round-trip regression tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from blueprint_document import decode
from blueprint_encoder import encode_document
from blueprint_library_store import DEFAULT_VERSION, BlueprintLibraryStore


def blueprint(label: str):
    return {"blueprint": {
        "version": DEFAULT_VERSION,
        "label": label,
        "entities": [{"entity_number": 1, "name": "transport-belt",
                      "position": {"x": 0, "y": 0}}],
    }}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = BlueprintLibraryStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_save_restart_and_export_preserves_document(self):
        doc = blueprint("Belts")
        item = self.store.save(doc, label="Belts")
        restarted = BlueprintLibraryStore(self.root)
        self.assertEqual(restarted.get(item), doc)
        self.assertEqual(decode(restarted.get_exchange(item)), doc)
        self.assertEqual(restarted.list_items()[0]["folder"], "My Blueprints")

    def test_book_append_remove_and_nested_round_trip(self):
        item = self.store.save(blueprint("Belts"))
        book_id = self.store.create_book("Starter Book")
        index = self.store.add_to_book(book_id, item)
        self.assertEqual(index, 0)
        source = self.store.get(book_id)
        self.assertEqual(source["blueprint_book"]["blueprints"][0]["blueprint"]["label"], "Belts")
        self.assertEqual(len(source["blueprint_book"]["blueprints"]), 1)
        other_book = self.store.create_book("Combined")
        self.store.add_to_book(other_book, book_id)
        self.assertIn("blueprint_book",
                      self.store.get(other_book)["blueprint_book"]["blueprints"][0])
        self.assertTrue(self.store.remove_book_item(book_id, 0))
        self.assertEqual(self.store.get(book_id)["blueprint_book"]["blueprints"], [])

    def test_cannot_add_book_to_itself(self):
        book_id = self.store.create_book("Mine")
        with self.assertRaisesRegex(ValueError, "itself"):
            self.store.add_to_book(book_id, book_id)

    def test_import_existing_exchange_and_rename(self):
        encoded = encode_document(blueprint("Imported"))
        item = self.store.import_exchange(encoded)
        self.store.rename(item, "Renamed")
        self.assertEqual(self.store.entries[item]["label"], "Renamed")
        self.assertEqual(self.store.get(item)["blueprint"]["label"], "Renamed")

    def test_invalid_input_refused_without_persistent_record(self):
        with self.assertRaises(ValueError):
            self.store.import_exchange("garbage")
        self.assertFalse(self.store.entries)

    def test_path_is_uuid_not_based_on_untrusted_label(self):
        identifier = self.store.save(blueprint("Test"), label="Name")
        self.assertTrue((self.root / (identifier + ".txt")).exists())
        self.assertEqual(len(identifier), 32)


if __name__ == "__main__":
    unittest.main()
