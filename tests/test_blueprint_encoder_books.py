"""R07-B tests: book fidelity, numeric safety and fail-closed encoding.

Offline only. These tests never read a user save, never call the game and
never perform network access.

The blueprint book is the hardest structure for a faithful encoder: it can
nest, its entry order and its ``index`` values are meaningful, and a nested
book must not be flattened, renamed or dropped. These tests assert exact
values, not merely an equivalent blueprint.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blueprint_codec import BlueprintError  # noqa: E402
from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402
from test_blueprint_encoder import (  # noqa: E402
    VERSION_2_0_10,
    VERSION_2_0_76,
    genuine_blueprint,
)


class NonFiniteNumberTests(unittest.TestCase):
    """A non-finite number can never reach the encoder output."""

    def test_non_finite_numbers_are_rejected(self):
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(BlueprintError):
                document = genuine_blueprint()
                document["blueprint"]["entities"][0]["position"]["x"] = value
                encode_document(document)

    def test_a_non_finite_number_in_a_book_entry_is_rejected(self):
        document = {
            "blueprint_book": {
                "version": VERSION_2_0_76,
                "blueprints": [
                    {
                        "blueprint": {
                            "version": VERSION_2_0_10,
                            "entities": [],
                        },
                        "index": 0,
                    }
                ],
            }
        }
        document["blueprint_book"]["blueprints"][0]["blueprint"]["scale"] = float("inf")
        with self.assertRaises(BlueprintError):
            encode_document(document)


class NestedBookTests(unittest.TestCase):
    """Nested books keep their structure, order and entry indexes."""

    def test_nested_books_retain_their_structure_and_order(self):
        document = {
            "blueprint_book": {
                "item": "blueprint-book",
                "blueprints": [
                    {
                        "blueprint": {
                            "item": "blueprint",
                            "label": "Second",
                            "entities": [],
                            "version": VERSION_2_0_10,
                        },
                        "index": 5,
                    },
                    {
                        "blueprint_book": {
                            "item": "blueprint-book",
                            "blueprints": [
                                {
                                    "blueprint": {
                                        "item": "blueprint",
                                        "label": "Inner",
                                        "entities": [],
                                        "version": VERSION_2_0_10,
                                    },
                                    "index": 0,
                                }
                            ],
                            "active_index": 0,
                            "version": VERSION_2_0_76,
                        },
                        "index": 1,
                    },
                ],
                "active_index": 1,
                "version": VERSION_2_0_76,
            }
        }
        decoded = decode(encode_document(document))
        self.assertEqual(decoded, document)
        entries = decoded["blueprint_book"]["blueprints"]
        self.assertEqual([entry["index"] for entry in entries], [5, 1])
        self.assertEqual(entries[0]["blueprint"]["label"], "Second")
        self.assertIn("blueprint_book", entries[1])
        self.assertEqual(
            entries[1]["blueprint_book"]["blueprints"][0]["blueprint"]["label"], "Inner"
        )
        self.assertEqual(decoded["blueprint_book"]["active_index"], 1)

    def test_an_empty_book_is_accepted_like_the_decoder_accepts_it(self):
        # The R07-A document layer accepts a book with an empty entry list, so
        # the encoder must accept it too. Refusing a document the decoder
        # accepts would break the fail-closed symmetry in the other direction.
        document = {
            "blueprint_book": {
                "version": VERSION_2_0_76,
                "blueprints": [],
            }
        }
        self.assertEqual(decode(encode_document(document)), document)


class FailClosedTests(unittest.TestCase):
    """A malformed document is refused before any bytes are written."""

    def test_oversized_or_malformed_inputs_fail_closed(self):
        for document in (
            {},
            {"blueprint": {}},
            {"blueprint": {"version": "not-an-int"}},
            {"blueprint": {"version": 1, "entities": "not-a-list"}},
            {"blueprint_book": {"version": VERSION_2_0_76}},
            {"blueprint_book": {"version": VERSION_2_0_76, "blueprints": "not-a-list"}},
            {"blueprint_book": {"version": VERSION_2_0_76, "blueprints": [
                {"garbage": 123}]}},
            {"blueprint_book": {"version": VERSION_2_0_76, "blueprints": [
                {"blueprint": {"version": VERSION_2_0_10}}]}},
            {"blueprint": {"version": VERSION_2_0_10}, "blueprint_book": {
                "version": VERSION_2_0_76, "blueprints": []}},
        ):
            with self.subTest(document=sorted(document)), self.assertRaises(BlueprintError):
                encode_document(document)

    def test_a_malformed_book_entry_is_refused(self):
        document = {
            "blueprint_book": {
                "version": VERSION_2_0_76,
                "blueprints": [
                    {"blueprint": {"version": VERSION_2_0_10, "entities": []},
                     "index": "not-an-int"}
                ],
            }
        }
        with self.assertRaises(BlueprintError):
            encode_document(document)

    def test_a_book_nested_beyond_the_depth_bound_is_refused(self):
        # A book nested deeper than the document layer allows must be refused
        # exactly as the decoder refuses it.
        document = {
            "blueprint_book": {
                "version": VERSION_2_0_76,
                "blueprints": [],
            }
        }
        inner = document["blueprint_book"]
        for _ in range(12):
            nested = {
                "blueprint_book": {
                    "version": VERSION_2_0_76,
                    "blueprints": [],
                }
            }
            inner["blueprints"] = [{"blueprint_book": nested, "index": 0}]
            inner = nested["blueprint_book"]
        with self.assertRaises(BlueprintError):
            encode_document(document)


if __name__ == "__main__":
    unittest.main()
