"""R07-A tests: numeric safety at the JSON parse boundary.

Offline only. These tests pin the rule that every number the decoder accepts
is finite, so that a later encoder can never have to serialise a NaN or an
Infinity that the game cannot represent.

The defect this file pins: ``json.loads(..., parse_constant=...)`` refuses the
non-standard literals ``NaN`` and ``Infinity``, but a *standard* numeric
literal can still overflow the float range. ``1e309`` converts to ``inf`` and
was accepted by the decoder, which would have let an unrepresentable value
reach the document layer and, later, the encoder output.
"""
import base64
import json
import math
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from blueprint_codec import BlueprintError, decode_payload  # noqa: E402


def encode_raw(payload: bytes) -> str:
    """Wrap raw bytes in the qualified exchange container."""
    return "0" + base64.b64encode(zlib.compress(payload)).decode("ascii")


def number_literal(text: str) -> bytes:
    """Build a one-member JSON object holding a numeric literal."""
    return ('{"v":' + text + "}").encode("ascii")


class NumericOverflowTests(unittest.TestCase):
    def test_refuses_a_positive_overflow(self):
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(number_literal("1e309")))

    def test_refuses_a_negative_overflow(self):
        with self.assertRaises(BlueprintError):
            decode_payload(encode_raw(number_literal("-1e309")))

    def test_refuses_huge_exponents(self):
        for text in ("1e309", "1e400", "1e1000", "1e99999", "-1e1000"):
            with self.subTest(text=text), self.assertRaises(BlueprintError):
                decode_payload(encode_raw(number_literal(text)))

    def test_accepts_an_underflowing_exponent_as_zero(self):
        # Underflow is not a safety defect. ``1e-99999`` is a finite value that
        # rounds to zero, so it is accepted; only an overflow to infinity is
        # refused.
        value = decode_payload(encode_raw(number_literal("1e-99999")))["v"]
        self.assertEqual(value, 0.0)
        self.assertTrue(math.isfinite(value))

    def test_refuses_an_overflow_in_every_json_position(self):
        payloads = (
            b"1e309",
            b"[1e309]",
            b'{"a":{"b":1e309}}',
            b'{"a":[1.0,1e309,2.0]}',
            b'{"a":"x","b":1e309}',
        )
        for payload in payloads:
            with self.subTest(payload=payload[:24]), self.assertRaises(BlueprintError):
                decode_payload(encode_raw(payload))

    def test_refuses_the_non_standard_literals_too(self):
        for text in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(text=text), self.assertRaises(BlueprintError):
                decode_payload(encode_raw(number_literal(text)))


class FiniteValueTests(unittest.TestCase):
    def test_accepts_the_largest_finite_double(self):
        value = decode_payload(encode_raw(number_literal("1.7976931348623157e308")))["v"]
        self.assertTrue(math.isfinite(value))

    def test_accepts_ordinary_fractional_values(self):
        for text, expected in (
            ("0.5", 0.5),
            ("-0.25", -0.25),
            ("1234567.891011", 1234567.891011),
            ("5e-324", 5e-324),
            ("1e-308", 1e-308),
        ):
            with self.subTest(text=text):
                value = decode_payload(encode_raw(number_literal(text)))["v"]
                self.assertEqual(value, expected)
                self.assertTrue(math.isfinite(value))

    def test_preserves_negative_zero(self):
        # Negative zero is finite and distinct from positive zero, so it is
        # accepted and preserved rather than normalised away.
        value = decode_payload(encode_raw(number_literal("-0.0")))["v"]
        self.assertEqual(value, 0.0)
        self.assertEqual(str(value), "-0.0")
        self.assertEqual(math.copysign(1.0, value), -1.0)

    def test_keeps_integers_as_integers(self):
        value = decode_payload(encode_raw(number_literal("562949954076672")))["v"]
        self.assertIsInstance(value, int)
        self.assertNotIsInstance(value, bool)
        self.assertEqual(value, 562949954076672)

    def test_every_accepted_number_is_finite(self):
        for text in ("0.5", "-0.0", "1e308", "562949954076672", "1e-320", "3"):
            with self.subTest(text=text):
                value = decode_payload(encode_raw(number_literal(text)))["v"]
                self.assertTrue(math.isfinite(value))


class EncoderReadyNumberTests(unittest.TestCase):
    """The decoded document must be serialisable without a non-finite token.

    ``json.dumps`` writes a bare ``Infinity`` or ``NaN`` token by default,
    which is not JSON. The encoder must therefore serialise with
    ``allow_nan=False``. This test proves the precondition that makes that
    safe: a decoded document cannot contain a non-finite number at all.
    """

    def test_a_decoded_document_dumps_with_allow_nan_false(self):
        document = decode_payload(encode_raw(b'{"a":1.5,"b":-0.0,"c":7}'))
        text = json.dumps(document, allow_nan=False)
        self.assertNotIn("Infinity", text)
        self.assertNotIn("NaN", text)

    def test_no_decoded_document_contains_a_non_finite_number(self):
        def walk(value):
            if isinstance(value, dict):
                for item in value.values():
                    yield from walk(item)
            elif isinstance(value, list):
                for item in value:
                    yield from walk(item)
            elif isinstance(value, float):
                yield value

        for text in ("0.5", "-0.0", "1e308", "1e-320", "2.5"):
            with self.subTest(text=text):
                document = decode_payload(encode_raw(number_literal(text)))
                for number in walk(document):
                    self.assertTrue(math.isfinite(number))


if __name__ == "__main__":
    unittest.main()
