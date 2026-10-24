"""R07-A tests: bounded, hostile-input-safe blueprint exchange container.

The decoder is offline only. These tests never read a user save and never call
the game.

Fixture provenance
------------------
The "genuine format" fixtures below are not invented by this test module. They
reproduce the container and document shapes produced by the pinned upstream
reference implementation:

* ``FactorioMCP/Services/BlueprintCodecService.cs`` -- ``ZlibCompress``
  writes the RFC 1950 header ``0x78 0x01``, a raw deflate stream, then a
  big-endian Adler-32 checksum; ``EncodeBlueprintString`` emits
  ``"0" + Convert.ToBase64String(compressed)``.
* ``FactorioMCP.Tests/Services/BlueprintCodecServiceTests.cs`` -- the
  ``MakeBlueprintString`` helper builds the same container, and the asserted
  blueprint JSON literals there (schema ``version`` 562949954076672, entity
  shapes, the blueprint-book shape) are the reference document shapes.

CPython's ``zlib.compress`` emits the same RFC 1950 container (``0x78 0x9c``
header, deflate body, Adler-32 trailer), so these are real game-format
exchange strings, not a private dialect.
"""
import base64
import json
import math
import sys
import unittest
import zlib
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import blueprint_codec  # noqa: E402
from blueprint_codec import BlueprintError, decode_payload, recognize  # noqa: E402

# Factorio 2.0.10 and 2.0.76 blueprint schema versions, as the game encodes
# them: (major << 48) | (minor << 32) | (build << 16) | revision.
VERSION_2_0_10 = 562949954076672
VERSION_2_0_76 = 562949958402048


def encode(document) -> str:
    """Produce a qualified Factorio blueprint exchange string for a document."""
    raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
    return "0" + base64.b64encode(zlib.compress(raw)).decode("ascii")


def encode_raw(payload: bytes) -> str:
    """Wrap raw bytes in the qualified exchange container."""
    return "0" + base64.b64encode(zlib.compress(payload)).decode("ascii")


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
                    "position": {"x": 1.5, "y": 0.5},
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


class RecognitionTests(unittest.TestCase):
    def test_recognizes_the_only_qualified_prefix(self):
        self.assertEqual(recognize(encode(genuine_blueprint())), ("0", "zlib"))

    def test_refuses_unqualified_or_malformed_prefixes(self):
        # The game emits exactly one prefix: "0". Every other leading character
        # is refused rather than guessed.
        for value in ("", "   ", "zz" + "A" * 20, "2" + "A" * 20, "x" + "A" * 20):
            with self.subTest(value=value[:4]), self.assertRaises(BlueprintError):
                recognize(value)

    def test_refuses_the_undocumented_stored_prefix(self):
        # "1" was never a Factorio exchange format; uncompressed payloads are
        # not a documented variant and must not be accepted.
        raw = json.dumps(genuine_blueprint()).encode("utf-8")
        stored = "1" + base64.b64encode(raw).decode("ascii")
        with self.assertRaises(BlueprintError):
            recognize(stored)
        with self.assertRaises(BlueprintError):
            decode_payload(stored)

    def test_refuses_a_prefix_with_no_payload(self):
        for value in ("0", "1"):
            with self.subTest(value=value), self.assertRaises(BlueprintError):
                recognize(value)

    def test_refuses_non_text_and_whitespace_padded_payloads(self):
        with self.assertRaises(BlueprintError):
            # A non-text payload must be refused rather than crash.
            recognize(cast(Any, None))
        with self.assertRaises(BlueprintError):
            recognize(" " + encode(genuine_blueprint()))

    def test_refuses_oversized_encoded_payload(self):
        with self.assertRaises(BlueprintError):
            recognize("0" + "A" * (blueprint_codec.MAX_ENCODED_CHARS + 4))


class DecodePayloadTests(unittest.TestCase):
    def test_decodes_a_genuine_blueprint_document(self):
        document = decode_payload(encode(genuine_blueprint()))
        self.assertEqual(document["blueprint"]["version"], VERSION_2_0_10)
        self.assertEqual(len(document["blueprint"]["entities"]), 2)
        self.assertEqual(
            document["blueprint"]["entities"][0]["position"], {"x": 0.5, "y": 0.5}
        )

    def test_decodes_a_genuine_blueprint_book_document(self):
        document = decode_payload(encode(genuine_book()))
        self.assertEqual(document["blueprint_book"]["version"], VERSION_2_0_76)
        self.assertEqual(document["blueprint_book"]["active_index"], 0)
        self.assertEqual(
            document["blueprint_book"]["blueprints"][0]["blueprint"]["label"], "Sub BP"
        )

    def test_refuses_raw_json_under_the_qualified_prefix(self):
        # A "0" prefix still requires a zlib container; raw JSON is refused by
        # the decompression step.
        raw = json.dumps(genuine_blueprint()).encode("utf-8")
        with self.assertRaises(BlueprintError):
            decode_payload("0" + base64.b64encode(raw).decode("ascii"))

    def test_decodes_any_valid_json_value(self):
        for payload in (b'"text"', b"123", b"[1,2,3]"):
            self.assertIsNotNone(decode_payload(encode_raw(payload)))

    def test_preserves_unknown_top_level_fields(self):
        document = genuine_blueprint()
        document["future_field"] = {"anything": [1, 2, 3]}
        self.assertEqual(
            decode_payload(encode(document))["future_field"], {"anything": [1, 2, 3]}
        )

    def test_preserves_unknown_entity_fields(self):
        document = genuine_blueprint()
        document["blueprint"]["entities"][0]["future_entity_field"] = "keep-me"
        decoded = decode_payload(encode(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][0]["future_entity_field"], "keep-me"
        )


class StrictJsonTests(unittest.TestCase):
    def test_refuses_duplicate_object_keys(self):
        payload = b'{"blueprint":{"version":1},"blueprint":{"version":2}}'
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(payload))

    def test_refuses_nan_and_infinity(self):
        for literal in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(literal=literal), self.assertRaises(BlueprintError):
                decode_payload(encode_raw(b'{"value":' + literal + b"}"))

    def test_refuses_nan_inside_an_array(self):
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(b"[1, NaN, 2]"))

    def test_refuses_a_malformed_document(self):
        for payload in (b"{", b"[1,", b'{"a":}'):
            with self.subTest(payload=payload), self.assertRaises(BlueprintError):
                decode_payload(encode_raw(payload))


class FiniteNumberTests(unittest.TestCase):
    """Every accepted numeric value must be finite.

    The non-standard literals NaN and Infinity are refused by ``parse_constant``,
    but a standard numeric literal can still overflow the float range: ``1e309``
    converts to infinity. Such a value must be refused at the parsing boundary,
    because an encoder could not serialise it without emitting a non-finite
    token that the game cannot represent.
    """

    def test_refuses_a_positive_numeric_overflow(self):
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(b'{"value":1e309}'))

    def test_refuses_a_negative_numeric_overflow(self):
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(b'{"value":-1e309}'))

    def test_refuses_very_large_exponents(self):
        # 1e308 is the largest finite magnitude a double can hold and is
        # accepted below; these exponents all overflow to infinity.
        for literal in (b"1e309", b"1e400", b"1e1000", b"1e99999", b"-1e1000"):
            with self.subTest(literal=literal), self.assertRaises(BlueprintError):
                decode_payload(encode_raw(b'{"value":' + literal + b"}"))

    def test_refuses_an_overflow_inside_an_array(self):
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(b"[1.0, 1e309, 2.0]"))

    def test_refuses_an_overflow_as_a_bare_document(self):
        # A bare numeric document is still a numeric document.
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(b"1e309"))

    def test_accepts_valid_finite_fractional_values(self):
        for literal, expected in (
            (b"0.5", 0.5),
            (b"-0.25", -0.25),
            (b"1.7976931348623157e308", 1.7976931348623157e308),
            (b"5e-324", 5e-324),
            (b"1234567.891011", 1234567.891011),
        ):
            with self.subTest(literal=literal):
                document = decode_payload(encode_raw(b'{"value":' + literal + b"}"))
                self.assertEqual(document["value"], expected)

    def test_preserves_negative_zero(self):
        # Negative zero is finite and is a distinct IEEE-754 value, so it is
        # accepted and preserved rather than silently normalised to 0.0.
        document = decode_payload(encode_raw(b'{"value":-0.0}'))
        value = document["value"]
        self.assertEqual(value, 0.0)
        self.assertEqual(str(value), "-0.0")

    def test_accepts_ordinary_integers_without_a_float_conversion(self):
        document = decode_payload(encode_raw(b'{"value":562949954076672}'))
        self.assertIsInstance(document["value"], int)
        self.assertEqual(document["value"], 562949954076672)

    def test_every_accepted_number_is_finite(self):
        for literal in (b"0.5", b"-0.0", b"1e308", b"562949954076672", b"1e-320"):
            with self.subTest(literal=literal):
                document = decode_payload(encode_raw(b'{"value":' + literal + b'}'))
                self.assertTrue(math.isfinite(document["value"]))


class DeeplyNestedJsonTests(unittest.TestCase):
    """A deeply nested payload must be refused, never crash the parser.

    The JSON scanner recurses once per nesting level, so a payload nested
    thousands of levels deep exhausts the interpreter stack *inside*
    ``json.loads``. That surfaces as ``RecursionError``, which is not a
    ``ValueError`` and therefore escaped the codec's error handling as an
    uncontrolled exception. The codec must convert it into a
    ``BlueprintError`` with an explicit reason.
    """

    # Deep enough to exhaust the JSON scanner's stack, shallow enough to stay
    # well inside the compressed and decoded size limits, so the refusal is
    # genuinely about nesting and not about size.
    NESTING_DEPTH = 5000

    def _nested_payload(self, depth: int) -> bytes:
        return ("[" * depth + "]" * depth).encode("ascii")

    def test_refuses_a_deeply_nested_array_as_a_blueprint_error(self):
        encoded = encode_raw(self._nested_payload(self.NESTING_DEPTH))
        with self.assertRaises(BlueprintError) as caught:
            decode_payload(encoded)
        self.assertIn("nested too deeply", str(caught.exception))

    def test_refuses_a_deeply_nested_object_as_a_blueprint_error(self):
        depth = self.NESTING_DEPTH
        payload = ('{"a":' * depth + "1" + "}" * depth).encode("ascii")
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(payload))

    def test_never_raises_an_uncontrolled_recursion_error(self):
        # The specific regression: before the fix this raised RecursionError.
        for depth in (self.NESTING_DEPTH, self.NESTING_DEPTH * 2):
            with self.subTest(depth=depth):
                try:
                    decode_payload(encode_raw(self._nested_payload(depth)))
                except BlueprintError:
                    pass
                except RecursionError as exc:  # pragma: no cover - regression
                    self.fail(f"RecursionError escaped the codec: {exc}")

    def test_refuses_a_nested_payload_that_stays_inside_the_size_limits(self):
        # The refusal must not depend on the size limits: this payload is far
        # below both the compressed and the decoded byte limits.
        raw = self._nested_payload(self.NESTING_DEPTH)
        compressed = zlib.compress(raw)
        self.assertLess(len(compressed), blueprint_codec.MAX_COMPRESSED_BYTES)
        self.assertLess(len(raw), blueprint_codec.MAX_DECOMPRESSED_BYTES)

    def test_still_accepts_a_shallowly_nested_document(self):
        # The fix must not refuse ordinary nesting.
        document = decode_payload(encode_raw(b'{"a":{"b":[1,2,{"c":3}]}}'))
        self.assertEqual(document["a"]["b"][2]["c"], 3)


if __name__ == "__main__":
    unittest.main()
