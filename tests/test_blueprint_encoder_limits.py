"""R07-B tests: the encoder's own size limits.

Offline only. These tests never read a user save, never call the game and
never perform network access.

The encoder must never emit a string the R07-A decoder would refuse for size.
It therefore reuses the decoder's own bounds rather than declaring its own,
and it applies them to the JSON text, the compressed payload and the encoded
string separately.

Reaching the compressed limit needs data that does not compress. A repeated
filler compresses to almost nothing and base-62 random text still compresses
to roughly three quarters of its length, because deflate encodes a 62-symbol
alphabet below eight bits per character. The full Unicode range is used
instead, so that each character carries close to eight bits of entropy.
"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import blueprint_encoder  # noqa: E402
from blueprint_codec import (  # noqa: E402
    MAX_COMPRESSED_BYTES,
    MAX_DECOMPRESSED_BYTES,
    MAX_ENCODED_CHARS,
    BlueprintError,
    decode_payload,
)
from blueprint_encoder import encode_document  # noqa: E402
from blueprint_property_fixtures import SEED  # noqa: E402
from test_blueprint_encoder import VERSION_2_0_10  # noqa: E402


def _document_with_filler(filler: str) -> dict[str, object]:
    return {
        "blueprint": {
            "version": VERSION_2_0_10,
            "entities": [],
            "filler": filler,
        }
    }


class DecodedLimitTests(unittest.TestCase):
    """A document whose JSON text is too large is refused."""

    def test_a_document_over_the_decoded_size_limit_is_refused(self):
        document = _document_with_filler("x" * (MAX_DECOMPRESSED_BYTES + 1024))
        with self.assertRaises(BlueprintError):
            encode_document(document)


class CompressedLimitTests(unittest.TestCase):
    """A document whose deflated payload is too large is refused."""

    def test_a_document_over_the_compressed_size_limit_is_refused(self):
        rng = random.Random(SEED + 5)
        filler = "".join(
            chr(rng.randrange(0x80, 0x2FF)) for _ in range(MAX_COMPRESSED_BYTES + 4096)
        )
        document = _document_with_filler(filler)
        with self.assertRaises(BlueprintError):
            encode_document(document)


class EncodedLengthTests(unittest.TestCase):
    """The encoded string length is bounded by the decoder's own limit."""

    def test_the_encoder_reuses_the_decoder_bounds(self):
        # The encoder must import the decoder's constants rather than
        # declaring its own, so the two can never drift apart.
        self.assertEqual(
            blueprint_encoder.MAX_ENCODED_CHARS, MAX_ENCODED_CHARS
        )
        self.assertEqual(
            blueprint_encoder.MAX_COMPRESSED_BYTES, MAX_COMPRESSED_BYTES
        )
        self.assertEqual(
            blueprint_encoder.MAX_DECOMPRESSED_BYTES, MAX_DECOMPRESSED_BYTES
        )

    def test_an_ordinary_document_is_far_inside_the_encoded_limit(self):
        document = _document_with_filler("x" * 1024)
        encoded = encode_document(document)
        self.assertLessEqual(len(encoded), MAX_ENCODED_CHARS)
        self.assertTrue(encoded.startswith("0"))


class CompressibleDocumentTests(unittest.TestCase):
    """A large but compressible document is accepted, because the decoder
    would accept it too. Refusing it would break the fail-closed symmetry in
    the other direction: the encoder must not refuse what the decoder allows.
    """

    def test_a_compressible_document_under_the_limit_is_accepted(self):
        document = _document_with_filler("x" * (MAX_COMPRESSED_BYTES + 1024))
        encoded = encode_document(document)
        self.assertLessEqual(len(encoded), MAX_ENCODED_CHARS)
        self.assertIsInstance(decode_payload(encoded), dict)


if __name__ == "__main__":
    unittest.main()
