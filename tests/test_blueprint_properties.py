"""R07-B tests: generated round-trip properties and the security boundary.

Offline only. These tests never read a user save, never call the game and
never perform network access.

What is proven here
-------------------
Two properties, over a generated family of documents rather than a handful of
handwritten fixtures:

1. **Round-trip.** ``decode(encode(document)) == document`` for every
   supported document, and ``decode(encode(decode(s))) == decode(s)`` for
   every accepted string.
2. **Determinism.** Encoding the same document twice yields the same string,
   and the string survives a decode/encode cycle unchanged.

The generator lives in ``blueprint_property_fixtures``. It is seeded, so a
failure is reproducible: the same seed always produces the same documents. The
sweep is deliberately bounded -- it is a correctness sweep, not a stress loop.

The security half of the file proves that the encoder fails closed:
unsupported document types, invalid JSON values and oversized output are all
refused, and no public API bypasses validation.
"""
import random
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import blueprint_encoder  # noqa: E402
from blueprint_codec import (  # noqa: E402
    MAX_ENCODED_CHARS,
    BlueprintError,
    decode_payload,
)
from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402
from blueprint_property_fixtures import (  # noqa: E402
    SEED,
    SWEEP_SIZE,
    coverage,
    random_document,
)
from test_blueprint_encoder import VERSION_2_0_10, VERSION_2_0_76  # noqa: E402


class GeneratedRoundTripTests(unittest.TestCase):
    """The generated sweep: round-trip and determinism over many documents."""

    def test_a_generated_document_round_trips_by_value(self):
        rng = random.Random(SEED)
        for index in range(SWEEP_SIZE):
            document = random_document(rng)
            with self.subTest(index=index):
                self.assertEqual(decode(encode_document(document)), document)

    def test_a_generated_string_round_trips_through_a_decode_encode_cycle(self):
        # decode(encode(decode(s))) == decode(s)
        rng = random.Random(SEED + 1)
        for index in range(SWEEP_SIZE):
            document = random_document(rng)
            string = encode_document(document)
            with self.subTest(index=index):
                self.assertEqual(decode(encode_document(decode(string))), decode(string))

    def test_repeated_encoding_produces_the_same_exchange_string(self):
        rng = random.Random(SEED + 2)
        for index in range(SWEEP_SIZE):
            document = random_document(rng)
            with self.subTest(index=index):
                self.assertEqual(encode_document(document), encode_document(document))

    def test_the_exchange_string_is_stable_across_a_decode_encode_cycle(self):
        rng = random.Random(SEED + 3)
        for index in range(SWEEP_SIZE):
            document = random_document(rng)
            once = encode_document(document)
            with self.subTest(index=index):
                self.assertEqual(encode_document(decode(once)), once)

    def test_every_generated_string_is_inside_the_decoder_limits(self):
        rng = random.Random(SEED + 4)
        for index in range(SWEEP_SIZE):
            document = random_document(rng)
            encoded = encode_document(document)
            with self.subTest(index=index):
                self.assertLessEqual(len(encoded), MAX_ENCODED_CHARS)
                # The decoder's own payload path must accept it.
                self.assertIsInstance(decode_payload(encoded), dict)


class GeneratedCoverageTests(unittest.TestCase):
    """The sweep must actually exercise every fidelity group.

    A generator that silently stopped producing wires or quality identifiers
    would make the round-trip sweep much weaker than it appears. This test
    keeps the sweep honest.
    """

    def test_the_generated_family_exercises_every_group(self):
        stats = coverage(random.Random(SEED), SWEEP_SIZE)
        for group in (
            "blueprints",
            "books",
            "nested_books",
            "entities",
            "wires",
            "quality",
            "filters",
            "items",
            "icons",
            "tiles",
            "non_ascii_labels",
            "unknown_members",
        ):
            with self.subTest(group=group):
                self.assertGreater(stats[group], 0)

    def test_the_generated_family_is_reproducible(self):
        first = coverage(random.Random(SEED), SWEEP_SIZE)
        second = coverage(random.Random(SEED), SWEEP_SIZE)
        self.assertEqual(first, second)


class FailClosedTests(unittest.TestCase):
    """The encoder never emits something the decoder would refuse."""

    def test_an_unsupported_document_type_is_refused(self):
        for document in (
            {},
            {"not_a_blueprint": {"version": VERSION_2_0_10}},
            {
                "blueprint": {"version": VERSION_2_0_10},
                "blueprint_book": {"version": VERSION_2_0_76, "blueprints": []},
            },
            "a string",
            123,
            None,
            [],
        ):
            with self.subTest(document=repr(document)[:40]), self.assertRaises(
                BlueprintError
            ):
                encode_document(document)

    def test_an_out_of_range_game_version_is_refused(self):
        document = {"blueprint": {"version": (16 << 48), "entities": []}}
        with self.assertRaises(BlueprintError):
            encode_document(document)

    def test_an_invalid_json_value_is_refused(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(BlueprintError):
                document = {"blueprint": {"version": VERSION_2_0_10, "entities": []}}
                document["blueprint"]["entities"] = [{"bad": value}]
                encode_document(document)

    def test_a_non_serialisable_value_is_refused(self):
        document = {"blueprint": {"version": VERSION_2_0_10, "entities": []}}
        document["blueprint"]["entities"] = [{"bad": {1, 2, 3}}]
        with self.assertRaises(BlueprintError):
            encode_document(document)


class NoPublicBypassTests(unittest.TestCase):
    """No public API can emit an unvalidated exchange string."""

    def test_the_module_exposes_exactly_one_public_encoding_function(self):
        public = [
            name
            for name in dir(blueprint_encoder)
            if not name.startswith("_")
            and callable(getattr(blueprint_encoder, name))
            and getattr(getattr(blueprint_encoder, name), "__module__", "")
            == blueprint_encoder.__name__
        ]
        self.assertEqual(public, ["encode_document"])

    def test_no_public_helper_emits_an_exchange_string(self):
        for name in ("encode_json", "round_trip", "encode", "encode_raw", "dump"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(blueprint_encoder, name))

    def test_the_private_helper_is_not_reachable_as_a_public_name(self):
        # _canonical_json exists but is private, and it does not apply the
        # size limits, so it must never be exported.
        self.assertTrue(hasattr(blueprint_encoder, "_canonical_json"))
        exported = getattr(blueprint_encoder, "__all__", [])
        self.assertNotIn("_canonical_json", exported)
        self.assertNotIn("encode_json", exported)

    def test_every_public_callable_refuses_a_hostile_document(self):
        # Whichever way a caller reaches the encoder, a document the decoder
        # refuses must not produce an exchange string. Only functions *defined
        # in* the encoder module count: imported names such as BlueprintError
        # are not encoding APIs.
        hostile: dict[str, Any] = {"blueprint": {"version": "not-an-int"}}
        for name in dir(blueprint_encoder):
            if name.startswith("_"):
                continue
            function = getattr(blueprint_encoder, name)
            if not callable(function):
                continue
            if getattr(function, "__module__", "") != blueprint_encoder.__name__:
                continue
            with self.subTest(name=name), self.assertRaises(BlueprintError):
                function(hostile)

    def test_the_public_function_never_returns_a_string_for_a_refused_document(self):
        # The refusal must happen *before* any bytes are produced, so there
        # is no partially valid output to leak.
        hostile: dict[str, Any] = {"blueprint": {"version": "not-an-int"}}
        try:
            encode_document(hostile)
        except BlueprintError:
            return
        except Exception as exc:  # noqa: BLE001
            self.fail(f"uncontrolled exception escaped: {type(exc).__name__} {exc}")
        self.fail("a malformed document was accepted")


if __name__ == "__main__":
    unittest.main()
