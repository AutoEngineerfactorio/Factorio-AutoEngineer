"""R07-B tests: the canonical JSON contract of the encoder.

Offline only. These tests never read a user save, never call the game and
never perform network access.

Why golden tests
-----------------
The R07-B plan requires that the JSON text is deterministic and that the *only*
normalisations are key ordering and separator whitespace. A round-trip test
alone cannot prove that: it would still pass if the encoder silently reformatted
every float, pruned an unknown field or renumbered an entity, as long as the
values survived. These tests pin the exact JSON bytes so that any change in the
serialisation is visible.

The golden strings below are the **observed** output of the encoder, not a
guess. They were captured by running the encoder and recording its result.
"""
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blueprint_document import decode  # noqa: E402
from blueprint_encoder import _canonical_json, encode_document  # noqa: E402
from test_blueprint_encoder import VERSION_2_0_10  # noqa: E402


class GoldenJsonTests(unittest.TestCase):
    """The exact JSON text produced for a fixed set of documents."""

    def test_keys_are_sorted_and_separators_are_compact(self):
        self.assertEqual(_canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')
        self.assertEqual(
            _canonical_json({"z": {"y": 1, "x": 2}, "a": [{"q": 1, "p": 2}]}),
            '{"a":[{"p":2,"q":1}],"z":{"x":2,"y":1}}',
        )

    def test_no_whitespace_is_emitted(self):
        text = _canonical_json(
            {"blueprint": {"version": VERSION_2_0_10, "entities": [{"name": "x"}]}}
        )
        self.assertNotIn(" ", text)
        self.assertNotIn("\n", text)
        self.assertNotIn("\t", text)

    def test_unicode_is_written_raw_not_escaped(self):
        # ensure_ascii=False: the text is UTF-8 and matches the game's shape.
        self.assertEqual(
            _canonical_json({"label": "Lärm 中文"}),
            '{"label":"Lärm 中文"}',
        )
        self.assertEqual(_canonical_json({"emoji": "\U0001f600"}), '{"emoji":"\U0001f600"}')

    def test_unicode_keys_are_sorted_by_code_point(self):
        self.assertEqual(
            _canonical_json({"中文": 1, "a": 2, "\U0001f600": 3}),
            '{"a":2,"中文":1,"\U0001f600":3}',
        )

    def test_control_characters_are_escaped(self):
        self.assertEqual(
            _canonical_json({"s": 'quote" back\\slash newline\n tab\t'}),
            '{"s":"quote\\" back\\\\slash newline\\n tab\\t"}',
        )

    def test_integers_stay_integer_tokens(self):
        self.assertEqual(
            _canonical_json({"version": VERSION_2_0_10, "n": 1}),
            '{"n":1,"version":562949954076672}',
        )

    def test_a_large_integer_beyond_float_precision_is_exact(self):
        # 9007199254740993 is 2**53 + 1 and is not representable as a float.
        # It must survive as an exact integer token, never as 9007199254740992.
        self.assertEqual(
            _canonical_json({"big": 9007199254740993}), '{"big":9007199254740993}'
        )

    def test_finite_float_formatting_is_stable(self):
        self.assertEqual(_canonical_json({"f": 1.5, "g": 0.1}), '{"f":1.5,"g":0.1}')
        self.assertEqual(
            _canonical_json({"f": 0.1234567890123456789, "h": 1e300, "i": 1e-300}),
            '{"f":0.12345678901234568,"h":1e+300,"i":1e-300}',
        )

    def test_a_whole_float_keeps_its_fractional_form(self):
        # 1.0 must not collapse to 1, or a float would become an integer.
        self.assertEqual(_canonical_json({"f": 1.0}), '{"f":1.0}')

    def test_negative_zero_is_preserved_in_the_text(self):
        self.assertEqual(_canonical_json({"z": -0.0}), '{"z":-0.0}')
        self.assertEqual(_canonical_json({"z": 0}), '{"z":0}')

    def test_booleans_and_null_are_emitted_as_json_literals(self):
        self.assertEqual(_canonical_json({"b": True, "c": False}), '{"b":true,"c":false}')
        self.assertEqual(_canonical_json({"n": None}), '{"n":null}')

    def test_empty_containers_are_emitted_compactly(self):
        self.assertEqual(_canonical_json({}), "{}")
        self.assertEqual(_canonical_json({"l": []}), '{"l":[]}')


class CanonicalJsonRoundTripTests(unittest.TestCase):
    """The canonical text is what the decoder reads back."""

    def test_the_emitted_text_is_what_the_decoder_reads(self):
        document = {
            "blueprint": {
                "item": "blueprint",
                "label": "Lärm 中文 \U0001f600",
                "version": VERSION_2_0_10,
                "entities": [
                    {
                        "entity_number": 1,
                        "name": "transport-belt",
                        "position": {"x": -0.0, "y": 0.5},
                        "direction": 4,
                    }
                ],
            }
        }
        encoded = encode_document(document)
        self.assertEqual(decode(encoded), document)

    def test_repeated_encoding_produces_the_same_exchange_string(self):
        document = {
            "blueprint": {
                "item": "blueprint",
                "label": "Deterministic",
                "version": VERSION_2_0_10,
                "entities": [],
            }
        }
        first = encode_document(document)
        second = encode_document(document)
        self.assertEqual(first, second)
        # And the canonical text behind it is identical too.
        self.assertEqual(_canonical_json(document), _canonical_json(document))

    def test_key_insertion_order_does_not_change_the_output(self):
        # Key ordering is the one normalisation the plan allows, so the same
        # members in a different insertion order must produce the same bytes.
        first = {"b": 1, "a": 2, "c": 3}
        second = {"c": 3, "b": 1, "a": 2}
        self.assertEqual(_canonical_json(first), _canonical_json(second))

    def test_list_order_is_never_normalised(self):
        # A list is ordered data, not a set: the order must survive.
        first = _canonical_json({"l": [3, 1, 2]})
        second = _canonical_json({"l": [1, 2, 3]})
        self.assertNotEqual(first, second)
        self.assertEqual(first, '{"l":[3,1,2]}')

    def test_unknown_fields_are_present_in_the_canonical_text(self):
        document: dict[str, Any] = {
            "blueprint": {
                "version": VERSION_2_0_10,
                "entities": [],
                "future_member": "keep-me",
            },
            "future_top_level": {"nested": [1, 2, 3]},
        }
        text = _canonical_json(document)
        self.assertIn('"future_member":"keep-me"', text)
        self.assertIn('"future_top_level":{"nested":[1,2,3]}', text)


if __name__ == "__main__":
    unittest.main()
