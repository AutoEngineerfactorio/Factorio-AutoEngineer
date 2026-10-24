"""R07-A tests: blueprint and blueprint book structure recognition.

Offline only. The fixtures use the real game schema-version integers and the
document shapes from the pinned upstream reference implementation
(``FactorioMCP.Tests/Services/BlueprintCodecServiceTests.cs``).
"""
import base64
import json
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import blueprint_document  # noqa: E402
from blueprint_codec import BlueprintError  # noqa: E402
from blueprint_document import classify, decode, describe  # noqa: E402

# Real Factorio 2.0 blueprint schema versions as the game encodes them.
VERSION_2_0_10 = 562949954076672
VERSION_2_0_76 = 562949958402048


def encode(document) -> str:
    raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
    return "0" + base64.b64encode(zlib.compress(raw)).decode("ascii")


def minimal_blueprint():
    return {
        "blueprint": {
            "item": "blueprint",
            "version": VERSION_2_0_10,
            "entities": [],
            "tiles": [],
        }
    }


def minimal_book():
    return {
        "blueprint_book": {
            "item": "blueprint-book",
            "version": VERSION_2_0_76,
            "blueprints": [],
        }
    }


class StructureRejectionTests(unittest.TestCase):
    def test_refuses_unknown_top_level_schema_variants(self):
        for document in ({"type": "upgrade_planner"}, {"type": "deconstruction_planner"},
                         {"type": "parameters"}, {"type": "something-else"}):
            with self.subTest(document=document["type"]), self.assertRaises(BlueprintError):
                decode(encode(document))

    def test_refuses_conflicting_top_level_blueprint_types(self):
        document = minimal_blueprint()
        document["blueprint_book"] = minimal_book()["blueprint_book"]
        with self.assertRaises(BlueprintError):
            decode(encode(document))
        with self.assertRaises(BlueprintError):
            classify(document)

    def test_refuses_an_unsupported_game_version(self):
        # The major version occupies the high 16 bits, so a version at or
        # above 16 << 48 cannot be a game version.
        for version in (-1, 1 << 60, (16 << 48)):
            document = minimal_blueprint()
            document["blueprint"]["version"] = version
            with self.subTest(version=version), self.assertRaises(BlueprintError):
                decode(encode(document))

    def test_refuses_a_non_integer_game_version(self):
        for version in ("1", "562949954076672", None, 1.5, [1], {"v": 1}):
            document = minimal_blueprint()
            document["blueprint"]["version"] = version
            with self.subTest(version=version), self.assertRaises(BlueprintError):
                decode(encode(document))

    def test_refuses_a_boolean_game_version(self):
        # bool is a subclass of int, so True must not pass as version 1.
        for version in (True, False):
            document = minimal_blueprint()
            document["blueprint"]["version"] = version
            with self.subTest(version=version), self.assertRaises(BlueprintError):
                decode(encode(document))

    def test_refuses_a_missing_game_version(self):
        document = minimal_blueprint()
        document["blueprint"].pop("version")
        with self.assertRaises(BlueprintError):
            decode(encode(document))

    def test_refuses_a_non_list_entities_or_tiles(self):
        for key in ("entities", "tiles"):
            document = minimal_blueprint()
            document["blueprint"][key] = "not-a-list"
            with self.subTest(key=key), self.assertRaises(BlueprintError):
                decode(encode(document))

    def test_refuses_a_malformed_structure(self):
        for document in (
            {"blueprint": "not-an-object"},
            {"blueprint_book": "not-an-object"},
            {"blueprint": {"version": VERSION_2_0_10, "entities": "x", "tiles": []}},
            {"blueprint_book": {"version": VERSION_2_0_76, "blueprints": "x"}},
        ):
            with self.subTest(document=str(document)[:40]), self.assertRaises(BlueprintError):
                classify(document)

    def test_refuses_hostile_nesting(self):
        deep: dict = {}
        cursor = deep
        for _ in range(blueprint_document.MAX_JSON_DEPTH + 10):
            child: dict = {}
            cursor["nested"] = child
            cursor = child
        with self.assertRaises(BlueprintError):
            classify({"blueprint": {"version": VERSION_2_0_10, "entities": [], "tiles": []},
                      "future_field": deep})

    def test_refuses_an_oversized_container(self):
        with self.assertRaises(BlueprintError):
            classify({
                "blueprint": {"version": VERSION_2_0_10, "entities": [], "tiles": []},
                "future_field": ["x"] * (blueprint_document.MAX_JSON_CONTAINER_ITEMS + 1),
            })


class OptionalMemberTests(unittest.TestCase):
    def test_accepts_a_blueprint_without_entities_or_tiles(self):
        # The game omits both members for an empty blueprint.
        document = {"blueprint": {"item": "blueprint", "version": VERSION_2_0_10}}
        decoded = decode(encode(document))
        self.assertEqual(decoded["blueprint"]["version"], VERSION_2_0_10)
        self.assertNotIn("entities", decoded["blueprint"])
        self.assertNotIn("tiles", decoded["blueprint"])

    def test_accepts_a_blueprint_with_only_entities(self):
        document = {"blueprint": {"version": VERSION_2_0_10, "entities": []}}
        self.assertEqual(classify(document), "blueprint")

    def test_accepts_a_blueprint_with_only_tiles(self):
        document = {"blueprint": {"version": VERSION_2_0_10, "tiles": []}}
        self.assertEqual(classify(document), "blueprint")


class ClassificationTests(unittest.TestCase):
    def test_recognizes_a_blueprint(self):
        document = decode(encode(minimal_blueprint()))
        self.assertEqual(document["blueprint"]["version"], VERSION_2_0_10)
        self.assertEqual(document["blueprint"]["entities"], [])
        self.assertEqual(document["blueprint"]["tiles"], [])

    def test_recognizes_a_blueprint_book(self):
        document = decode(encode(minimal_book()))
        self.assertEqual(document["blueprint_book"]["version"], VERSION_2_0_76)
        self.assertEqual(document["blueprint_book"]["blueprints"], [])

    def test_decode_does_not_insert_a_synthetic_key(self):
        document = decode(encode(minimal_blueprint()))
        self.assertNotIn("_decoded_kind", document)
        self.assertNotIn("_decoded_kind", document["blueprint"])

    def test_describe_returns_metadata_separately(self):
        metadata = describe(minimal_blueprint())
        self.assertEqual(metadata["kind"], "blueprint")
        self.assertEqual(metadata["version"], VERSION_2_0_10)
        self.assertEqual(metadata["entity_count"], 0)
        self.assertEqual(metadata["tile_count"], 0)

    def test_describe_reports_a_book(self):
        metadata = describe(minimal_book())
        self.assertEqual(metadata["kind"], "blueprint_book")
        self.assertEqual(metadata["version"], VERSION_2_0_76)
        self.assertEqual(metadata["blueprint_count"], 0)

    def test_describe_counts_entities(self):
        document = minimal_blueprint()
        document["blueprint"]["entities"] = [
            {"entity_number": 1, "name": "transport-belt", "position": {"x": 0, "y": 0}},
        ]
        self.assertEqual(describe(document)["entity_count"], 1)

    def test_preserves_unknown_fields_for_round_trip(self):
        document = minimal_blueprint()
        document["future_field"] = {"anything": [1, 2, 3]}
        document["blueprint"]["future_inner"] = "keep-me"
        decoded = decode(encode(document))
        self.assertEqual(decoded["future_field"], {"anything": [1, 2, 3]})
        self.assertEqual(decoded["blueprint"]["future_inner"], "keep-me")


class BookEntryValidationTests(unittest.TestCase):
    """A book is not accepted on the strength of its top-level shape alone."""

    def test_accepts_a_book_with_a_valid_blueprint_entry(self):
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [
            {"blueprint": {"item": "blueprint", "version": VERSION_2_0_10,
                           "entities": [], "tiles": []}, "index": 0}
        ]
        self.assertEqual(classify(document), "blueprint_book")

    def test_refuses_a_non_object_entry(self):
        for entry in ("not-an-object", 12, None, ["blueprint"]):
            document = minimal_book()
            document["blueprint_book"]["blueprints"] = [entry]
            with self.subTest(entry=entry), self.assertRaises(BlueprintError):
                classify(document)

    def test_refuses_an_entry_with_no_document_member(self):
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [{"index": 0, "label": "x"}]
        with self.assertRaises(BlueprintError):
            classify(document)

    def test_refuses_an_entry_with_conflicting_document_members(self):
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [
            {"blueprint": {"version": VERSION_2_0_10},
             "blueprint_book": {"version": VERSION_2_0_76, "blueprints": []},
             "index": 0}
        ]
        with self.assertRaises(BlueprintError):
            classify(document)

    def test_refuses_an_entry_with_a_missing_index(self):
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [
            {"blueprint": {"version": VERSION_2_0_10}}
        ]
        with self.assertRaises(BlueprintError):
            classify(document)

    def test_refuses_a_non_integer_index(self):
        for index in ("0", 1.5, True, False, None, [0], {"index": 0}):
            document = minimal_book()
            document["blueprint_book"]["blueprints"] = [
                {"blueprint": {"version": VERSION_2_0_10}, "index": index}
            ]
            with self.subTest(index=index), self.assertRaises(BlueprintError):
                classify(document)

    def test_refuses_a_negative_or_out_of_range_index(self):
        for index in (-1, blueprint_document.MAX_BOOK_INDEX + 1):
            document = minimal_book()
            document["blueprint_book"]["blueprints"] = [
                {"blueprint": {"version": VERSION_2_0_10}, "index": index}
            ]
            with self.subTest(index=index), self.assertRaises(BlueprintError):
                classify(document)

    def test_refuses_an_entry_whose_document_is_malformed(self):
        for payload in (
            {"version": VERSION_2_0_10, "entities": "not-a-list"},
            {"version": VERSION_2_0_10, "tiles": 5},
            {"version": "not-an-int"},
            {"entities": []},
            "not-an-object",
        ):
            document = minimal_book()
            document["blueprint_book"]["blueprints"] = [
                {"blueprint": payload, "index": 0}
            ]
            with self.subTest(payload=str(payload)[:32]), self.assertRaises(BlueprintError):
                classify(document)

    def test_accepts_a_nested_book_within_the_depth_bound(self):
        # Factorio supports a blueprint book inside a blueprint book, so a
        # nested book is validated recursively rather than refused.
        nested = minimal_book()
        nested["blueprint_book"]["blueprints"] = [
            {"blueprint": {"version": VERSION_2_0_10, "entities": []}, "index": 0}
        ]
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [
            {"blueprint_book": nested["blueprint_book"], "index": 0}
        ]
        self.assertEqual(classify(document), "blueprint_book")

    def test_refuses_a_nested_book_beyond_the_depth_bound(self):
        # Build a book nested deeper than the bound allows.
        payload = minimal_book()["blueprint_book"]
        payload["blueprints"] = [{"blueprint": {"version": VERSION_2_0_10}, "index": 0}]
        for _ in range(blueprint_document.MAX_BOOK_DEPTH + 2):
            payload = {
                "version": VERSION_2_0_76,
                "blueprints": [{"blueprint_book": payload, "index": 0}],
            }
        document = {"blueprint_book": payload}
        with self.assertRaises(BlueprintError):
            classify(document)

    def test_refuses_an_oversized_book_entry_list(self):
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [
            {"blueprint": {"version": VERSION_2_0_10}, "index": 0}
        ] * (blueprint_document.MAX_BOOK_ENTRIES + 1)
        with self.assertRaises(BlueprintError):
            classify(document)


class BookFidelityTests(unittest.TestCase):
    """Order, indexes, active selection and unknown members must survive."""

    def test_preserves_entry_order_and_indexes(self):
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [
            {"blueprint": {"version": VERSION_2_0_10, "label": "third"}, "index": 7},
            {"blueprint": {"version": VERSION_2_0_10, "label": "first"}, "index": 2},
            {"blueprint": {"version": VERSION_2_0_10, "label": "second"}, "index": 5},
        ]
        decoded = decode(encode(document))
        entries = decoded["blueprint_book"]["blueprints"]
        self.assertEqual([e["index"] for e in entries], [7, 2, 5])
        self.assertEqual([e["blueprint"]["label"] for e in entries],
                         ["third", "first", "second"])

    def test_preserves_the_active_index(self):
        document = minimal_book()
        document["blueprint_book"]["active_index"] = 3
        decoded = decode(encode(document))
        self.assertEqual(decoded["blueprint_book"]["active_index"], 3)

    def test_preserves_unknown_book_and_entry_members(self):
        document = minimal_book()
        document["blueprint_book"]["future_book_member"] = {"a": [1, 2]}
        document["blueprint_book"]["blueprints"] = [
            {"blueprint": {"version": VERSION_2_0_10}, "index": 0,
             "future_entry_member": "keep-me"}
        ]
        decoded = decode(encode(document))
        self.assertEqual(decoded["blueprint_book"]["future_book_member"], {"a": [1, 2]})
        self.assertEqual(
            decoded["blueprint_book"]["blueprints"][0]["future_entry_member"], "keep-me"
        )

    def test_describe_counts_book_entries(self):
        document = minimal_book()
        document["blueprint_book"]["blueprints"] = [
            {"blueprint": {"version": VERSION_2_0_10}, "index": 0},
            {"blueprint": {"version": VERSION_2_0_10}, "index": 1},
        ]
        self.assertEqual(describe(document)["blueprint_count"], 2)


if __name__ == "__main__":
    unittest.main()
