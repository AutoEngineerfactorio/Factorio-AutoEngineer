"""R07-B tests: the Unicode contract of the codec and the encoder.

Offline only. These tests never read a user save, never call the game and
never perform network access.

Why this file exists
--------------------
An independent review reproduced a defect in the R07-B encoder:

1. a Factorio-format container holding an escaped lone Unicode surrogate such
   as ``\\ud800`` was accepted by the R07-A decoder;
2. passing the decoded document into ``encode_document()`` raised
   ``UnicodeEncodeError``, an uncontrolled exception rather than a refusal;
3. a valid surrogate pair round-tripped correctly.

The contract now is: malformed Unicode is **refused** with ``BlueprintError``
at the decode boundary and at the encode boundary. It is never silently
replaced with U+FFFD and never discarded, because the game would then import
a different blueprint than the one that was exported. Valid Unicode -- ordinary
non-ASCII text, emoji written as a surrogate pair, and every other well-formed
string -- must survive a round-trip exactly, by value.
"""
import base64
import sys
import unittest
import zlib
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blueprint_codec import (  # noqa: E402
    BlueprintError,
    check_text_unicode,
    decode_payload,
)
from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402
from test_blueprint_encoder import VERSION_2_0_10  # noqa: E402

# The escaped lone surrogates that the JSON grammar permits but UTF-8 cannot
# represent. A high surrogate must be followed by a low surrogate; a low
# surrogate must be preceded by a high one.
LONE_HIGH_SURROGATES = ("\\ud800", "\\ud83d", "\\udbff")
LONE_LOW_SURROGATES = ("\\udc00", "\\ude00", "\\udfff")


def container(payload: bytes) -> str:
    """Build a genuine exchange string around a raw JSON payload."""
    return "0" + base64.b64encode(zlib.compress(payload, 9)).decode("ascii")


def blueprint_json(label_escape: str) -> bytes:
    """A blueprint document whose label carries the given JSON escape."""
    return (
        '{"blueprint":{"item":"blueprint","label":"'
        + label_escape
        + '","version":'
        + str(VERSION_2_0_10)
        + "}}"
    ).encode("utf-8")


class DecodeRefusesMalformedUnicodeTests(unittest.TestCase):
    """The decoder refuses an unpaired surrogate instead of accepting it."""

    def test_a_lone_high_surrogate_is_refused(self):
        for escape in LONE_HIGH_SURROGATES:
            with self.subTest(escape=escape):
                with self.assertRaises(BlueprintError) as caught:
                    decode_payload(container(blueprint_json(escape)))
                self.assertIn("surrogate", str(caught.exception))

    def test_a_lone_low_surrogate_is_refused(self):
        for escape in LONE_LOW_SURROGATES:
            with self.subTest(escape=escape):
                with self.assertRaises(BlueprintError) as caught:
                    decode_payload(container(blueprint_json(escape)))
                self.assertIn("surrogate", str(caught.exception))

    def test_a_surrogate_in_an_object_key_is_refused(self):
        payload = (
            '{"blueprint":{"item":"blueprint","bad\\ud800key":1,"version":'
            + str(VERSION_2_0_10)
            + "}}"
        ).encode("utf-8")
        with self.assertRaises(BlueprintError) as caught:
            decode_payload(container(payload))
        self.assertIn("surrogate", str(caught.exception))

    def test_a_surrogate_in_a_nested_value_is_refused(self):
        payload = (
            '{"blueprint":{"item":"blueprint","entities":[{"name":"x","nested":'
            '["ok","\\udc00bad"]}],"version":'
            + str(VERSION_2_0_10)
            + "}}"
        ).encode("utf-8")
        with self.assertRaises(BlueprintError) as caught:
            decode_payload(container(payload))
        self.assertIn("surrogate", str(caught.exception))

    def test_the_refusal_is_a_blueprint_error_not_an_uncaught_exception(self):
        # The defect was an uncontrolled UnicodeEncodeError escaping the
        # public API. The refusal must be a BlueprintError every time.
        try:
            decode(container(blueprint_json("\\ud800")))
        except BlueprintError:
            return
        except Exception as exc:  # noqa: BLE001
            self.fail(f"uncontrolled exception escaped: {type(exc).__name__} {exc}")
        self.fail("a lone surrogate was accepted")


class EncoderRefusesMalformedUnicodeTests(unittest.TestCase):
    """The encoder refuses a document it could not represent.

    The decoder is not the only way a document reaches the encoder: a caller
    can hand it a Python string directly. The encoder therefore carries its own
    independent barrier.
    """

    def _document(self, label: str) -> dict[str, Any]:
        return {
            "blueprint": {
                "item": "blueprint",
                "label": label,
                "version": VERSION_2_0_10,
            }
        }

    def test_a_lone_surrogate_in_a_value_is_refused(self):
        for label in ("bad\ud800label", "bad\udc00label", "\ud83d"):
            with self.subTest(label=repr(label)):
                with self.assertRaises(BlueprintError) as caught:
                    encode_document(self._document(label))
                self.assertIn("surrogate", str(caught.exception))

    def test_a_lone_surrogate_in_an_object_key_is_refused(self):
        document = self._document("fine")
        document["blueprint"]["bad\ud800key"] = 1
        with self.assertRaises(BlueprintError) as caught:
            encode_document(document)
        self.assertIn("surrogate", str(caught.exception))

    def test_the_refusal_is_a_blueprint_error_not_an_uncaught_exception(self):
        try:
            encode_document(self._document("bad\ud800label"))
        except BlueprintError:
            return
        except Exception as exc:  # noqa: BLE001
            self.fail(f"uncontrolled exception escaped: {type(exc).__name__} {exc}")
        self.fail("a lone surrogate was accepted")


class SharedUnicodePrimitiveTests(unittest.TestCase):
    """The shared primitive that both boundaries use."""

    def test_the_primitive_refuses_an_unpaired_surrogate(self):
        for text in ("\ud800", "\udc00", "ok\ud800bad", "ok\udc00bad"):
            with self.subTest(text=repr(text)):
                with self.assertRaises(BlueprintError):
                    check_text_unicode(text)

    def test_the_primitive_accepts_a_valid_surrogate_pair(self):
        check_text_unicode("\U0001f600")
        check_text_unicode("plain")
        check_text_unicode("")

    def test_the_primitive_refuses_a_non_text_argument(self):
        # A non-text argument must be refused cleanly, not raise an
        # uncontrolled TypeError or KeyError from the scan.
        for value in (None, 42, b"bytes", ["list"], {"key": "value"}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(BlueprintError):
                    check_text_unicode(value)


class ValidUnicodeIsPreservedTests(unittest.TestCase):
    """Well-formed Unicode survives a round-trip exactly, by value."""

    def _round_trip_label(self, label: str) -> str:
        document = {
            "blueprint": {
                "item": "blueprint",
                "label": label,
                "version": VERSION_2_0_10,
            }
        }
        decoded = decode(encode_document(document))
        return decoded["blueprint"]["label"]

    def test_a_valid_surrogate_pair_round_trips(self):
        # "\ud83d\ude00" is U+1F600 GRINNING FACE. The pair is a single
        # astral code point and must not be mistaken for malformed Unicode.
        label = "\U0001f600"
        self.assertEqual(self._round_trip_label(label), label)
        self.assertEqual(len(self._round_trip_label(label)), 1)

    def test_an_emoji_written_as_an_escape_round_trips(self):
        # The same emoji, but delivered through the JSON escape form.
        payload = blueprint_json("\\ud83d\\ude00")
        document = decode(container(payload))
        self.assertEqual(document["blueprint"]["label"], "\U0001f600")
        self.assertEqual(decode(encode_document(document)), document)

    def test_ordinary_non_ascii_text_round_trips(self):
        for label in ("Lärm 中文", "Ünïcödé", "Ελληνικά", "עברית", "Ünïcödé ✓"):
            with self.subTest(label=label):
                self.assertEqual(self._round_trip_label(label), label)

    def test_non_ascii_labels_are_not_normalised_away(self):
        # The encoder must not replace a non-ASCII label with an escape or an
        # ASCII transliteration; the value has to survive by value.
        label = "中文標籤"
        self.assertEqual(self._round_trip_label(label), label)

    def test_a_mixed_label_round_trips(self):
        label = "Start-中文-\U0001f600-End"
        self.assertEqual(self._round_trip_label(label), label)


if __name__ == "__main__":
    unittest.main()
