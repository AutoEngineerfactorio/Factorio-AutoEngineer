"""R07-B tests: the encoder's public surface and its fail-closed guarantees.

Offline only. These tests never read a user save, never call the game and
never perform network access.

The R07-B plan requires that exactly one public function produces an exchange
string and that it always validates first. A public escape hatch would let a
caller emit a document the R07-A decoder refuses, which would break the
fail-closed goal. These tests pin that shape.
"""
import math
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import blueprint_encoder  # noqa: E402
from blueprint_codec import BlueprintError, decode_payload  # noqa: E402
from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_blueprint_encoder import (  # noqa: E402
    VERSION_2_0_10,
    genuine_blueprint,
)


class PublicSurfaceTests(unittest.TestCase):
    def test_the_module_has_one_public_encoding_entry_point(self):
        public = [
            name
            for name in dir(blueprint_encoder)
            if not name.startswith("_")
            and callable(getattr(blueprint_encoder, name))
            and getattr(getattr(blueprint_encoder, name), "__module__", "")
            == blueprint_encoder.__name__
        ]
        self.assertEqual(public, ["encode_document"])

    def test_the_round_trip_helper_is_not_public(self):
        # Any helper that also emits a string must stay private.
        self.assertFalse(hasattr(blueprint_encoder, "round_trip"))
        self.assertFalse(hasattr(blueprint_encoder, "encode_json"))
        self.assertTrue(hasattr(blueprint_encoder, "_canonical_json"))

    def test_a_non_text_object_key_is_refused(self):
        document = genuine_blueprint()
        document["blueprint"][7] = "not-a-text-key"
        with self.assertRaises(BlueprintError):
            encode_document(document)

    def test_a_non_serialisable_value_is_refused(self):
        document = genuine_blueprint()
        document["blueprint"]["entities"][0]["custom"] = {1, 2, 3}
        with self.assertRaises(BlueprintError):
            encode_document(document)

    def test_the_emitted_string_respects_the_decoder_bounds(self):
        encoded = encode_document(genuine_blueprint())
        self.assertLessEqual(len(encoded), blueprint_encoder.MAX_ENCODED_CHARS)
        # The decoder's own payload path must accept it.
        self.assertIsInstance(decode_payload(encoded), dict)

    def test_a_deeply_nested_document_is_refused(self):
        # The document layer bounds nesting before any bytes are written.
        document: dict[str, Any] = {"blueprint": {"version": VERSION_2_0_10}}
        inner: dict[str, Any] = document
        for _ in range(200):
            child: dict[str, Any] = {}
            inner["entities"] = [child]
            inner = child
        with self.assertRaises(BlueprintError):
            encode_document(document)

    def test_negative_zero_survives_the_round_trip(self):
        document = genuine_blueprint()
        document["blueprint"]["entities"][0]["position"]["x"] = -0.0
        decoded = decode(encode_document(document))
        value = decoded["blueprint"]["entities"][0]["position"]["x"]
        self.assertEqual(value, 0.0)
        self.assertEqual(math.copysign(1.0, value), -1.0)


if __name__ == "__main__":
    unittest.main()
