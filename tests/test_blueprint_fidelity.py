"""R07-B tests: blueprint fidelity at the entity level.

Offline only. These tests never read a user save, never call the game and
never perform network access.

The R07-B plan requires that a round-trip preserves *exact values*, not merely
an equivalent blueprint. A document that "looks the same" is not enough: the
assertion must be on the individual member. These tests therefore read the
decoded document back and compare each fidelity group member by member.

Nothing is normalised: entity numbers are not renumbered, positions are not
snapped, directions are not re-encoded, recipes and filters are not resolved
to prototypes, and quality identifiers are not mapped to names. The encoder
treats every one of these as opaque data.

The shared fixture lives here so that the opaque-value groups in
``test_blueprint_fidelity_opaque.py`` can reuse it.
"""
import math
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402
from test_blueprint_encoder import VERSION_2_0_10  # noqa: E402


def rich_blueprint() -> dict[str, Any]:
    """A blueprint exercising every entity-level fidelity group.

    The member names and shapes follow the Factorio blueprint export format.
    The *values* are arbitrary but exact: the point of these tests is that the
    encoder copies them verbatim, not that they are plausible gameplay.
    """
    return {
        "blueprint": {
            "item": "blueprint",
            "label": "Fidelity Fixture",
            "label_color": {"r": 1.0, "g": 0.5, "b": 0.25, "a": 1.0},
            "icons": [
                {
                    "icon": "virtual-signal/circuit-network",
                    "icon_size": 1,
                    "flag": 0,
                    "order": "a-z",
                    "type": "item",
                }
            ],
            "version": VERSION_2_0_10,
            "entities": [
                {
                    "entity_number": 7,
                    "name": "transport-belt",
                    "position": {"x": 10.5, "y": -3.25},
                    "direction": 4,
                    "recipe": "iron-gear-wheel",
                },
                {
                    "entity_number": 12,
                    "name": "assembling-machine-1",
                    "position": {"x": -0.5, "y": 0.0},
                    "direction": 0,
                    "recipe": "advanced-circuit",
                    "recipe_quality": "legendary",
                    "filters": [
                        {"index": 1, "name": "electronic-circuit", "count": 12},
                        {"index": 2, "name": "advanced-circuit", "count": 4},
                    ],
                    "items": {
                        "electronic-circuit": {"count": 120, "amount": 1},
                        "advanced-circuit": {"count": 40, "amount": 1},
                    },
                    "quality": "epic",
                },
                {
                    "entity_number": 99,
                    "name": "fast-transport-belt",
                    "position": {"x": 0.0, "y": 0.0},
                    "direction": 14,
                    "unknown_entity_member": {"kept": [1, 2, {"deep": True}]},
                },
            ],
            "tiles": [
                {
                    "name": "concrete",
                    "position": {"x": 2.0, "y": 3.0},
                    "position2": {"x": 3.0, "y": 3.0},
                    "tile": "concrete",
                }
            ],
            "unknown_blueprint_member": "kept-verbatim",
        }
    }


class EntityNumberTests(unittest.TestCase):
    """Entity numbers are preserved exactly and never renumbered."""

    def test_entity_numbers_survive_in_order(self):
        decoded = decode(encode_document(rich_blueprint()))
        numbers = [
            entity["entity_number"] for entity in decoded["blueprint"]["entities"]
        ]
        self.assertEqual(numbers, [7, 12, 99])

    def test_non_sequential_entity_numbers_are_not_renumbered(self):
        document = rich_blueprint()
        document["blueprint"]["entities"] = [
            {"entity_number": 1000, "name": "x", "position": {"x": 0.0, "y": 0.0}},
            {"entity_number": 3, "name": "y", "position": {"x": 0.0, "y": 0.0}},
            {"entity_number": 42, "name": "z", "position": {"x": 0.0, "y": 0.0}},
        ]
        decoded = decode(encode_document(document))
        numbers = [
            entity["entity_number"] for entity in decoded["blueprint"]["entities"]
        ]
        self.assertEqual(numbers, [1000, 3, 42])

    def test_entity_order_is_never_rearranged(self):
        decoded = decode(encode_document(rich_blueprint()))
        names = [entity["name"] for entity in decoded["blueprint"]["entities"]]
        self.assertEqual(
            names, ["transport-belt", "assembling-machine-1", "fast-transport-belt"]
        )


class PositionTests(unittest.TestCase):
    """Positions are preserved exactly, including fractions and negatives."""

    def test_positions_are_preserved_exactly(self):
        decoded = decode(encode_document(rich_blueprint()))
        positions = [
            entity["position"] for entity in decoded["blueprint"]["entities"]
        ]
        self.assertEqual(positions[0], {"x": 10.5, "y": -3.25})
        self.assertEqual(positions[1], {"x": -0.5, "y": 0.0})
        self.assertEqual(positions[2], {"x": 0.0, "y": 0.0})

    def test_a_negative_zero_position_keeps_its_sign(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][0]["position"]["x"] = -0.0
        decoded = decode(encode_document(document))
        value = decoded["blueprint"]["entities"][0]["position"]["x"]
        self.assertEqual(value, 0.0)
        self.assertEqual(math.copysign(1.0, value), -1.0)

    def test_a_fractional_position_is_not_snapped_to_a_grid(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][0]["position"] = {
            "x": 10.123456,
            "y": -0.987654,
        }
        decoded = decode(encode_document(document))
        position = decoded["blueprint"]["entities"][0]["position"]
        self.assertEqual(position["x"], 10.123456)
        self.assertEqual(position["y"], -0.987654)


class DirectionTests(unittest.TestCase):
    """Directions are preserved as the integer the game uses."""

    def test_every_direction_value_survives(self):
        for direction in (0, 2, 4, 6, 8, 10, 12, 14):
            with self.subTest(direction=direction):
                document = rich_blueprint()
                document["blueprint"]["entities"][0]["direction"] = direction
                decoded = decode(encode_document(document))
                value = decoded["blueprint"]["entities"][0]["direction"]
                self.assertEqual(value, direction)
                self.assertIsInstance(value, int)
                self.assertNotIsInstance(value, bool)


class EntityTypePreservationTests(unittest.TestCase):
    """Numeric members keep their JSON type, not just their value."""

    def test_an_entity_number_stays_an_integer(self):
        decoded = decode(encode_document(rich_blueprint()))
        number = decoded["blueprint"]["entities"][0]["entity_number"]
        self.assertIsInstance(number, int)
        self.assertNotIsInstance(number, bool)

    def test_a_position_component_stays_a_float(self):
        decoded = decode(encode_document(rich_blueprint()))
        position = decoded["blueprint"]["entities"][0]["position"]
        self.assertIsInstance(position["x"], float)
        self.assertIsInstance(position["y"], float)

    def test_a_whole_position_component_is_not_turned_into_an_integer(self):
        # A position of 0.0 must stay 0.0. If it became the integer 0, the
        # game would still accept it, but the value would no longer be the
        # one that was exported.
        decoded = decode(encode_document(rich_blueprint()))
        position = decoded["blueprint"]["entities"][2]["position"]
        self.assertIsInstance(position["x"], float)
        self.assertIsInstance(position["y"], float)

    def test_the_game_version_stays_an_integer(self):
        decoded = decode(encode_document(rich_blueprint()))
        version = decoded["blueprint"]["version"]
        self.assertIsInstance(version, int)
        self.assertNotIsInstance(version, bool)
        self.assertEqual(version, VERSION_2_0_10)


class EntityNameTests(unittest.TestCase):
    """Entity prototype names are opaque strings and survive exactly."""

    def test_entity_names_are_preserved(self):
        decoded = decode(encode_document(rich_blueprint()))
        names = [entity["name"] for entity in decoded["blueprint"]["entities"]]
        self.assertEqual(
            names, ["transport-belt", "assembling-machine-1", "fast-transport-belt"]
        )

    def test_an_unknown_prototype_name_is_preserved(self):
        # The offline codec has no catalog, so it cannot reject a prototype
        # it does not know. It copies the name verbatim; prototype validation
        # is R07-D work.
        document = rich_blueprint()
        document["blueprint"]["entities"][0]["name"] = "modded-turret-xyz"
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][0]["name"], "modded-turret-xyz"
        )


if __name__ == "__main__":
    unittest.main()
