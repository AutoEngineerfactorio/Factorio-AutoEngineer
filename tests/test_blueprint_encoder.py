"""R07-B tests: focused acceptance for the faithful blueprint encoder.

Offline only. These tests never read a user save, never call the game and
never perform network access.

What is proven here
-------------------
The encoder emits a qualified exchange string that the corrected R07-A
decoder accepts, and the decoded document has the same values as the input.

What is NOT proven here
-----------------------
This is a *structural* proof. It says nothing about whether Factorio would
import the blueprint. Importability needs a genuine game-exported fixture and
a separately authorised read-only compatibility check; it is deliberately not
claimed by R07-B.
"""
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402

# Factorio 2.0.10 and 2.0.76 packed game versions.
VERSION_2_0_10 = 562949954076672
VERSION_2_0_76 = 562949958402048


def genuine_blueprint() -> dict[str, Any]:
    """A blueprint document in the shape the game actually emits."""
    return {
        "blueprint": {
            "item": "blueprint",
            "label": "Smelter Line",
            "entities": [
                {
                    "entity_number": 1,
                    "name": "transport-belt",
                    "position": {"x": 0.5, "y": 0.5},
                    "direction": 4,
                },
                {
                    "entity_number": 2,
                    "name": "assembling-machine-1",
                    "position": {"x": 1.5, "y": -0.25},
                    "recipe": "iron-gear-wheel",
                },
            ],
            "version": VERSION_2_0_10,
        }
    }


def genuine_book() -> dict[str, Any]:
    """A blueprint book in the shape the game actually emits."""
    return {
        "blueprint_book": {
            "item": "blueprint-book",
            "blueprints": [
                {
                    "blueprint": {
                        "item": "blueprint",
                        "label": "Sub BP",
                        "entities": [],
                        "version": VERSION_2_0_10,
                    },
                    "index": 0,
                }
            ],
            "active_index": 0,
            "version": VERSION_2_0_76,
        }
    }


class AcceptanceTests(unittest.TestCase):
    """The eight R07-B acceptance checks."""

    def test_the_decoder_accepts_the_encoded_string(self):
        # 1. The encoder creates a string the corrected R07-A decoder accepts.
        for document in (genuine_blueprint(), genuine_book()):
            with self.subTest(kind=sorted(document)):
                encoded = encode_document(document)
                self.assertIsInstance(encoded, str)
                self.assertTrue(encoded.startswith("0"))
                decoded = decode(encoded)
                self.assertIsInstance(decoded, dict)

    def test_the_decoded_document_equals_the_original_by_value(self):
        # 2. The decoded document equals the original by value.
        for document in (genuine_blueprint(), genuine_book()):
            with self.subTest(kind=sorted(document)):
                self.assertEqual(decode(encode_document(document)), document)

    def test_the_output_is_deterministic(self):
        # 3. Encoded output is deterministic for identical input.
        document = genuine_blueprint()
        self.assertEqual(encode_document(document), encode_document(document))
        # And stable across a decode/encode cycle.
        once = encode_document(document)
        twice = encode_document(decode(once))
        self.assertEqual(once, twice)

    def test_no_unknown_fields_are_discarded(self):
        # 4. No unknown fields are discarded.
        document = genuine_blueprint()
        document["future_top_level"] = {"anything": [1, 2, 3]}
        document["blueprint"]["future_member"] = "keep-me"
        document["blueprint"]["entities"][0]["future_entity_field"] = "keep-me-too"
        decoded = decode(encode_document(document))
        self.assertEqual(decoded["future_top_level"], {"anything": [1, 2, 3]})
        self.assertEqual(decoded["blueprint"]["future_member"], "keep-me")
        self.assertEqual(
            decoded["blueprint"]["entities"][0]["future_entity_field"], "keep-me-too"
        )

    def test_integers_remain_integers(self):
        # 5. Integers remain integers.
        decoded = decode(encode_document(genuine_blueprint()))
        version = decoded["blueprint"]["version"]
        self.assertIsInstance(version, int)
        self.assertNotIsInstance(version, bool)
        self.assertEqual(version, VERSION_2_0_10)
        number = decoded["blueprint"]["entities"][0]["entity_number"]
        self.assertIsInstance(number, int)
        self.assertEqual(number, 1)


if __name__ == "__main__":
    unittest.main()
