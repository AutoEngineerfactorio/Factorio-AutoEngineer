"""R07-B tests: blueprint book fidelity.

Offline only. These tests never read a user save, never call the game and
never perform network access.

A blueprint book is the structure most easily damaged by an encoder. Its
entry order, its ``index`` values and its nesting are all meaningful, and a
faithful encoder must not flatten a nested book, renumber the entries or
reorder the list. These tests assert the exact values, not merely that the
book still decodes.
"""
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blueprint_codec import BlueprintError  # noqa: E402
from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402
from test_blueprint_encoder import VERSION_2_0_10, VERSION_2_0_76  # noqa: E402


def entry(label: str, index: int) -> dict[str, Any]:
    """One blueprint book entry carrying a single blueprint."""
    return {
        "blueprint": {
            "item": "blueprint",
            "label": label,
            "entities": [],
            "version": VERSION_2_0_10,
        },
        "index": index,
    }


def book(entries: list[dict[str, Any]], active_index: int = 0) -> dict[str, Any]:
    """A blueprint book carrying the given entries."""
    return {
        "blueprint_book": {
            "item": "blueprint-book",
            "blueprints": entries,
            "active_index": active_index,
            "version": VERSION_2_0_76,
        }
    }


class EntryOrderTests(unittest.TestCase):
    """The order of the entry list is never changed."""

    def test_entry_order_is_preserved(self):
        document = book([entry("First", 0), entry("Second", 1), entry("Third", 2)])
        decoded = decode(encode_document(document))
        labels = [
            e["blueprint"]["label"] for e in decoded["blueprint_book"]["blueprints"]
        ]
        self.assertEqual(labels, ["First", "Second", "Third"])

    def test_entry_order_is_not_sorted_by_index(self):
        # The list order and the index values are independent. The encoder
        # must not sort the list to match the indexes.
        document = book([entry("Third", 2), entry("First", 0), entry("Second", 1)])
        decoded = decode(encode_document(document))
        entries = decoded["blueprint_book"]["blueprints"]
        self.assertEqual(
            [e["blueprint"]["label"] for e in entries], ["Third", "First", "Second"]
        )
        self.assertEqual([e["index"] for e in entries], [2, 0, 1])


class EntryIndexTests(unittest.TestCase):
    """Index values are preserved exactly and never renumbered."""

    def test_non_sequential_indexes_are_preserved(self):
        document = book([entry("A", 7), entry("B", 3), entry("C", 11)])
        decoded = decode(encode_document(document))
        indexes = [e["index"] for e in decoded["blueprint_book"]["blueprints"]]
        self.assertEqual(indexes, [7, 3, 11])

    def test_an_index_gap_is_preserved(self):
        document = book([entry("A", 0), entry("B", 5), entry("C", 9)])
        decoded = decode(encode_document(document))
        indexes = [e["index"] for e in decoded["blueprint_book"]["blueprints"]]
        self.assertEqual(indexes, [0, 5, 9])

    def test_a_large_index_is_preserved(self):
        document = book([entry("A", (1 << 31) - 1)])
        decoded = decode(encode_document(document))
        self.assertEqual(decoded["blueprint_book"]["blueprints"][0]["index"], (1 << 31) - 1)

    def test_an_index_stays_an_integer(self):
        document = book([entry("A", 4)])
        decoded = decode(encode_document(document))
        value = decoded["blueprint_book"]["blueprints"][0]["index"]
        self.assertIsInstance(value, int)
        self.assertNotIsInstance(value, bool)


class ActiveIndexTests(unittest.TestCase):
    """``active_index`` is preserved exactly."""

    def test_the_active_index_is_preserved(self):
        for active in (0, 1, 2, 7):
            with self.subTest(active_index=active):
                document = book(
                    [entry("A", 0), entry("B", 1), entry("C", 2)], active_index=active
                )
                decoded = decode(encode_document(document))
                self.assertEqual(decoded["blueprint_book"]["active_index"], active)

    def test_the_active_index_stays_an_integer(self):
        decoded = decode(encode_document(book([entry("A", 0)], active_index=0)))
        value = decoded["blueprint_book"]["active_index"]
        self.assertIsInstance(value, int)
        self.assertNotIsInstance(value, bool)


class NestedBookTests(unittest.TestCase):
    """A nested book keeps its structure; it is never flattened."""

    def test_a_nested_book_is_not_flattened(self):
        inner = book([entry("Inner", 0)])
        document = book([entry("Outer", 0), {"blueprint_book": inner["blueprint_book"], "index": 1}])
        decoded = decode(encode_document(document))
        entries = decoded["blueprint_book"]["blueprints"]
        self.assertIn("blueprint_book", entries[1])
        self.assertNotIn("blueprint", entries[1])
        self.assertEqual(
            entries[1]["blueprint_book"]["blueprints"][0]["blueprint"]["label"], "Inner"
        )

    def test_a_deeply_nested_book_keeps_its_full_depth(self):
        # Four levels of nesting must all survive.
        deepest = book([entry("Level4", 0)])
        level3 = book([{"blueprint_book": deepest["blueprint_book"], "index": 0}])
        level2 = book([{"blueprint_book": level3["blueprint_book"], "index": 0}])
        level1 = book([{"blueprint_book": level2["blueprint_book"], "index": 0}])
        decoded = decode(encode_document(level1))
        node = decoded["blueprint_book"]["blueprints"][0]["blueprint_book"]
        node = node["blueprints"][0]["blueprint_book"]
        node = node["blueprints"][0]["blueprint_book"]
        self.assertEqual(node["blueprints"][0]["blueprint"]["label"], "Level4")

    def test_a_nested_book_keeps_its_own_active_index(self):
        inner = book([entry("Inner", 0)], active_index=0)
        document = book([{"blueprint_book": inner["blueprint_book"], "index": 0}])
        decoded = decode(encode_document(document))
        nested = decoded["blueprint_book"]["blueprints"][0]["blueprint_book"]
        self.assertEqual(nested["active_index"], 0)

    def test_a_book_nested_beyond_the_depth_bound_is_refused(self):
        # The document layer bounds the nesting; the encoder must refuse a
        # book the decoder would also refuse.
        document = book([entry("A", 0)])
        inner = document["blueprint_book"]
        for _ in range(12):
            nested = {"blueprint_book": {"blueprints": [], "version": VERSION_2_0_76}}
            inner["blueprints"] = [{"blueprint_book": nested, "index": 0}]
            inner = nested["blueprint_book"]
        with self.assertRaises(BlueprintError):
            encode_document(document)


class UnknownFieldTests(unittest.TestCase):
    """Unknown but compatible fields survive in a book and in its entries."""

    def test_unknown_book_members_survive(self):
        document = book([entry("A", 0)])
        document["blueprint_book"]["future_book_member"] = {"kept": True}
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint_book"]["future_book_member"], {"kept": True}
        )

    def test_unknown_entry_members_survive(self):
        document = book([entry("A", 0)])
        document["blueprint_book"]["blueprints"][0]["future_entry_member"] = [1, 2, 3]
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint_book"]["blueprints"][0]["future_entry_member"], [1, 2, 3]
        )

    def test_an_unknown_top_level_member_survives(self):
        document = book([entry("A", 0)])
        document["future_top_level"] = "kept"
        decoded = decode(encode_document(document))
        self.assertEqual(decoded["future_top_level"], "kept")


if __name__ == "__main__":
    unittest.main()
