"""R07-B tests: fidelity of the opaque value groups.

Offline only. These tests never read a user save, never call the game and
never perform network access.

Recipes, filters, item quantities, quality identifiers, icons, tiles, labels
and unknown members are all *opaque* to the offline codec. The encoder has no
catalog, no prototype table and no game semantics, so it must copy each of
them verbatim. It must not resolve a recipe to a prototype, map a quality id
to a name, reorder a filter list, drop an icon or prune an unknown member.

The shared fixture comes from ``test_blueprint_fidelity``.
"""
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blueprint_document import decode  # noqa: E402
from blueprint_encoder import encode_document  # noqa: E402
from test_blueprint_fidelity import rich_blueprint  # noqa: E402


class RecipeAndFilterTests(unittest.TestCase):
    """Recipes and filters are opaque identifiers, never resolved."""

    def test_recipes_are_preserved_exactly(self):
        decoded = decode(encode_document(rich_blueprint()))
        entities = decoded["blueprint"]["entities"]
        self.assertEqual(entities[0]["recipe"], "iron-gear-wheel")
        self.assertEqual(entities[1]["recipe"], "advanced-circuit")

    def test_filters_are_preserved_including_their_order(self):
        decoded = decode(encode_document(rich_blueprint()))
        filters = decoded["blueprint"]["entities"][1]["filters"]
        self.assertEqual(
            filters,
            [
                {"index": 1, "name": "electronic-circuit", "count": 12},
                {"index": 2, "name": "advanced-circuit", "count": 4},
            ],
        )

    def test_item_quantities_are_preserved_exactly(self):
        decoded = decode(encode_document(rich_blueprint()))
        items = decoded["blueprint"]["entities"][1]["items"]
        self.assertEqual(
            items,
            {
                "electronic-circuit": {"count": 120, "amount": 1},
                "advanced-circuit": {"count": 40, "amount": 1},
            },
        )

    def test_a_filter_count_is_not_renormalised(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["filters"][0]["count"] = 0
        decoded = decode(encode_document(document))
        self.assertEqual(decoded["blueprint"]["entities"][1]["filters"][0]["count"], 0)

    def test_a_fractional_item_count_is_preserved(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["items"]["electronic-circuit"]["count"] = 12.5
        decoded = decode(encode_document(document))
        items = decoded["blueprint"]["entities"][1]["items"]
        self.assertEqual(items["electronic-circuit"]["count"], 12.5)


class QualityTests(unittest.TestCase):
    """Quality identifiers are opaque and are never mapped to names."""

    def test_quality_identifiers_are_preserved_exactly(self):
        decoded = decode(encode_document(rich_blueprint()))
        entities = decoded["blueprint"]["entities"]
        self.assertEqual(entities[1]["quality"], "epic")
        self.assertEqual(entities[1]["recipe_quality"], "legendary")

    def test_an_unknown_quality_identifier_is_preserved(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["quality"] = "quality-not-in-the-catalog"
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][1]["quality"], "quality-not-in-the-catalog"
        )


class IconsTilesAndLabelsTests(unittest.TestCase):
    """Icons, tiles, labels and label colours are preserved verbatim."""

    def test_icons_are_preserved_exactly(self):
        decoded = decode(encode_document(rich_blueprint()))
        self.assertEqual(
            decoded["blueprint"]["icons"],
            [
                {
                    "icon": "virtual-signal/circuit-network",
                    "icon_size": 1,
                    "flag": 0,
                    "order": "a-z",
                    "type": "item",
                }
            ],
        )

    def test_tiles_are_preserved_exactly(self):
        decoded = decode(encode_document(rich_blueprint()))
        self.assertEqual(
            decoded["blueprint"]["tiles"],
            [
                {
                    "name": "concrete",
                    "position": {"x": 2.0, "y": 3.0},
                    "position2": {"x": 3.0, "y": 3.0},
                    "tile": "concrete",
                }
            ],
        )

    def test_the_label_and_its_colour_are_preserved(self):
        decoded = decode(encode_document(rich_blueprint()))
        self.assertEqual(decoded["blueprint"]["label"], "Fidelity Fixture")
        self.assertEqual(
            decoded["blueprint"]["label_color"],
            {"r": 1.0, "g": 0.5, "b": 0.25, "a": 1.0},
        )


class UnknownMemberTests(unittest.TestCase):
    """Unknown but compatible fields survive at every level."""

    def test_unknown_members_at_every_level_survive(self):
        decoded = decode(encode_document(rich_blueprint()))
        self.assertEqual(
            decoded["blueprint"]["unknown_blueprint_member"], "kept-verbatim"
        )
        self.assertEqual(
            decoded["blueprint"]["entities"][2]["unknown_entity_member"],
            {"kept": [1, 2, {"deep": True}]},
        )

    def test_an_unknown_top_level_member_survives(self):
        document: dict[str, Any] = rich_blueprint()
        document["future_top_level"] = {"anything": [1, 2, 3]}
        decoded = decode(encode_document(document))
        self.assertEqual(decoded["future_top_level"], {"anything": [1, 2, 3]})


class WireAndCircuitTests(unittest.TestCase):
    """Wires and circuit connections are opaque and are never resolved.

    The encoder has no game semantics, so it does not renumber or validate
    wire endpoints. The endpoints stay exactly as supplied, including their
    order inside the nested list.
    """

    def _wired(self) -> dict[str, Any]:
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["wires"] = [
            [[12, 1], [7, 2]],
            [[12, 3], [99, 4]],
        ]
        return document

    def test_wires_are_preserved_exactly(self):
        decoded = decode(encode_document(self._wired()))
        wires = decoded["blueprint"]["entities"][1]["wires"]
        self.assertEqual(wires, [[[12, 1], [7, 2]], [[12, 3], [99, 4]]])

    def test_wire_endpoint_order_is_never_rearranged(self):
        document = self._wired()
        document["blueprint"]["entities"][1]["wires"] = [[[99, 4], [12, 3]]]
        decoded = decode(encode_document(document))
        wires = decoded["blueprint"]["entities"][1]["wires"]
        self.assertEqual(wires, [[[99, 4], [12, 3]]])

    def test_a_circuit_network_id_is_preserved(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["circuit_network_id"] = 12345
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][1]["circuit_network_id"], 12345
        )

    def test_a_connection_point_is_preserved(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["connection_points"] = [
            {"x": 0.5, "y": 0.5},
            {"x": 1.5, "y": 0.5},
        ]
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][1]["connection_points"],
            [{"x": 0.5, "y": 0.5}, {"x": 1.5, "y": 0.5}],
        )

    def test_a_signal_id_is_preserved_as_an_opaque_value(self):
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["signals"] = [
            {"type": "virtual", "name": "signal-A", "index": 1}
        ]
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][1]["signals"],
            [{"type": "virtual", "name": "signal-A", "index": 1}],
        )


class TrainScheduleTests(unittest.TestCase):
    """Train schedules and their stations survive verbatim.

    Times are not normalised and stations are not reordered: the schedule is
    a list of ordered records and the encoder copies it exactly.
    """

    def _scheduled(self) -> dict[str, Any]:
        document = rich_blueprint()
        document["blueprint"]["entities"][1]["schedule"] = {
            "record_type": "schedule",
            "wait_time": 30,
            "station": "iron-ore-station",
            "records": [
                {
                    "record_type": "wait",
                    "wait_time": 5,
                    "station": "copper-station",
                },
                {
                    "record_type": "travel",
                    "station": "iron-ore-station",
                    "wait_time": 0,
                },
            ],
            "start_wait_time": 10,
        }
        return document

    def test_a_train_schedule_is_preserved_exactly(self):
        decoded = decode(encode_document(self._scheduled()))
        schedule = decoded["blueprint"]["entities"][1]["schedule"]
        self.assertEqual(schedule["record_type"], "schedule")
        self.assertEqual(schedule["wait_time"], 30)
        self.assertEqual(schedule["station"], "iron-ore-station")
        self.assertEqual(schedule["start_wait_time"], 10)

    def test_schedule_records_keep_their_order(self):
        decoded = decode(encode_document(self._scheduled()))
        records = decoded["blueprint"]["entities"][1]["schedule"]["records"]
        self.assertEqual(
            [record["station"] for record in records],
            ["copper-station", "iron-ore-station"],
        )

    def test_a_schedule_time_is_not_normalised(self):
        document = self._scheduled()
        document["blueprint"]["entities"][1]["schedule"]["wait_time"] = 7.5
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][1]["schedule"]["wait_time"], 7.5
        )

    def test_a_station_name_is_preserved(self):
        document = self._scheduled()
        document["blueprint"]["entities"][1]["schedule"]["station"] = "中文站"
        decoded = decode(encode_document(document))
        self.assertEqual(
            decoded["blueprint"]["entities"][1]["schedule"]["station"], "中文站"
        )


if __name__ == "__main__":
    unittest.main()
