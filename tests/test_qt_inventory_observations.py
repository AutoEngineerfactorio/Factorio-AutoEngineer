"""Offline regression tests for the R10-B inventory observation snapshot.

The snapshot turns the ``autoengineer_inventory`` frame into the one
immutable object that the Qt workspaces and the AI Helper both read. The
tests pin the three rules that matter:

* an unobserved field is **unavailable**, never a zero;
* a bounded collection reports that it was truncated;
* two networks are never merged.

No game process, no save, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from qt_inventory_observations import (  # noqa: E402
    MAX_MACHINE_ROWS,
    MAX_NETWORK_ROWS,
    InventoryObservation,
    inventory_observation,
)
from qt_observation import OBSERVED, UNAVAILABLE  # noqa: E402


def machine_row(name: str = "assembling-machine-1",
                entity_type: str = "assembling-machine",
                surface: str = "nauvis",
                **extra) -> dict:
    """Return one observed machine row."""
    row = {
        "name": name,
        "type": entity_type,
        "surface": surface,
        "quality": "normal",
        "x": 10,
        "y": -20,
        "active": True,
        "recipe": "iron-gear-wheel",
        "inventories": [
            {
                "category": "ingredient",
                "identifier": "chest",
                "capacity": 4,
                "items": [
                    {"name": "iron-plate", "count": 100, "quality": "normal"},
                    {"name": "copper-plate", "count": 50, "quality": "rare"},
                ],
                "empty": False,
                "truncated": False,
            },
        ],
        "fluids": [],
    }
    row.update(extra)
    return row


def network_row(network_id: int = 1, surface: str = "nauvis",
                **extra) -> dict:
    """Return one observed logistic network row."""
    row = {
        "network_id": network_id,
        "surface": surface,
        "force": "player",
        "custom_name": "main",
        "available_logistic_robots": 120,
        "all_logistic_robots": 200,
        "available_construction_robots": 30,
        "all_construction_robots": 60,
        "robot_limit": 250,
        "items": [
            {"name": "iron-plate", "count": 5000, "quality": "normal"},
        ],
        "providers": ["provider-chest"],
        "requesters": ["requester-chest"],
        "storages": ["storage-chest"],
        "items_truncated": False,
    }
    row.update(extra)
    return row


def frame(**sections) -> dict:
    """Return one ``autoengineer_inventory`` frame."""
    payload = {
        "status": "ok",
        "protocol": 1,
        "tick": 1234,
        "surface": "nauvis",
        "machine_inventories": {
            "available": True,
            "status": "ok",
            "page": 1,
            "page_size": 16,
            "total": 1,
            "page_count": 1,
            "matched": 1,
            "partial": False,
            "truncated": False,
            "snapshot": "1234:1",
            "rows": [machine_row()],
        },
        "logistics": {
            "available": True,
            "status": "ok",
            "page": 1,
            "page_size": 16,
            "total": 1,
            "page_count": 1,
            "snapshot": "1234:1",
            "rows": [network_row()],
        },
        "robots": {
            "available": True,
            "status": "ok",
            "networks": 1,
            "total_logistic_robots": 200,
            "available_logistic_robots": 120,
            "total_construction_robots": 60,
            "available_construction_robots": 30,
            "robot_limit": 250,
            "partial": False,
        },
        "transport": {
            "available": True,
            "status": "ok",
            "page": 1,
            "page_size": 16,
            "total": 1,
            "page_count": 1,
            "matched": 1,
            "rows": [{
                "name": "cargo-wagon-1",
                "type": "cargo-wagon",
                "surface": "nauvis",
                "quality": "normal",
                "x": 3,
                "y": 3,
                "inventories": [{
                    "category": "ingredient",
                    "identifier": "cargo_wagon",
                    "capacity": 8,
                    "items": [
                        {"name": "iron-plate", "count": 400,
                         "quality": "normal"},
                    ],
                    "empty": False,
                    "truncated": False,
                }],
                "fluids": [],
            }],
        },
    }
    payload.update(sections)
    return payload


class InventoryObservationTests(unittest.TestCase):
    """The snapshot must report what the game reported and nothing else."""

    def test_an_absent_frame_is_unavailable(self):
        snapshot = inventory_observation(None)
        self.assertEqual(snapshot.state, UNAVAILABLE)
        self.assertFalse(snapshot.known)
        self.assertEqual(snapshot.machines_state, UNAVAILABLE)
        self.assertEqual(snapshot.machines, ())
        self.assertEqual(snapshot.networks, ())
        self.assertIsNone(snapshot.robots.total_logistic_robots)

    def test_a_machine_row_is_read(self):
        snapshot = inventory_observation(frame())
        self.assertEqual(snapshot.state, OBSERVED)
        self.assertEqual(len(snapshot.machines), 1)
        machine = snapshot.machines[0]
        self.assertEqual(machine.name, "assembling-machine-1")
        self.assertEqual(machine.entity_type, "assembling-machine")
        self.assertEqual(machine.surface, "nauvis")
        self.assertEqual(machine.quality, "normal")
        self.assertEqual(machine.x, 10)
        self.assertEqual(machine.y, -20)
        self.assertEqual(machine.recipe, "iron-gear-wheel")
        self.assertTrue(machine.active)

    def test_an_inventory_reports_the_items_the_capacities_and_the_quality(self):
        snapshot = inventory_observation(frame())
        inventory = snapshot.machines[0].inventories[0]
        self.assertEqual(inventory.category, "ingredient")
        self.assertEqual(inventory.identifier, "chest")
        self.assertEqual(inventory.capacity, 4)
        self.assertEqual(inventory.item_count, 2)
        items = {item.name: item for item in inventory.items}
        self.assertEqual(items["iron-plate"].count, 100)
        self.assertEqual(items["copper-plate"].quality, "rare")
        self.assertFalse(inventory.empty)

    def test_an_empty_inventory_is_empty_and_not_absent(self):
        payload = frame()
        payload["machine_inventories"]["rows"][0]["inventories"] = [{
            "category": "module",
            "identifier": "lab_modules",
            "capacity": 2,
            "items": [],
            "empty": True,
            "truncated": False,
        }]
        snapshot = inventory_observation(payload)
        inventory = snapshot.machines[0].inventories[0]
        self.assertTrue(inventory.empty)
        self.assertEqual(inventory.item_count, 0)
        self.assertEqual(inventory.capacity, 2)

    def test_a_machine_without_any_inventory_reports_none(self):
        payload = frame()
        payload["machine_inventories"]["rows"][0]["inventories"] = []
        snapshot = inventory_observation(payload)
        self.assertEqual(snapshot.machines[0].inventories, ())

    def test_a_fluid_inventory_reports_the_amount_and_the_temperature(self):
        payload = frame()
        payload["machine_inventories"]["rows"][0]["fluids"] = [{
            "name": "water", "amount": 500, "temperature": 15,
        }]
        snapshot = inventory_observation(payload)
        fluid = snapshot.machines[0].fluids[0]
        self.assertEqual(fluid.name, "water")
        self.assertEqual(fluid.amount, 500)
        self.assertEqual(fluid.temperature, 15)

    def test_a_network_is_read_with_its_items_and_its_members(self):
        snapshot = inventory_observation(frame())
        self.assertEqual(len(snapshot.networks), 1)
        network = snapshot.networks[0]
        self.assertEqual(network.network_id, 1)
        self.assertEqual(network.surface, "nauvis")
        self.assertEqual(network.custom_name, "main")
        self.assertEqual(network.items[0].name, "iron-plate")
        self.assertEqual(network.items[0].count, 5000)
        self.assertEqual(network.providers, ("provider-chest",))
        self.assertEqual(network.requesters, ("requester-chest",))
        self.assertEqual(network.storages, ("storage-chest",))

    def test_two_networks_are_never_merged(self):
        payload = frame()
        payload["logistics"]["rows"] = [
            network_row(1, items=[
                {"name": "iron-plate", "count": 5000, "quality": "normal"}]),
            network_row(2, "vulcanus", items=[
                {"name": "steel-plate", "count": 42, "quality": "normal"}]),
        ]
        snapshot = inventory_observation(payload)
        self.assertEqual(len(snapshot.networks), 2)
        first, second = snapshot.networks
        self.assertEqual(first.network_id, 1)
        self.assertEqual(second.network_id, 2)
        self.assertEqual(first.surface, "nauvis")
        self.assertEqual(second.surface, "vulcanus")
        self.assertEqual({item.name for item in first.items}
                         & {item.name for item in second.items}, set())

    def test_the_robot_counts_are_read(self):
        snapshot = inventory_observation(frame())
        robots = snapshot.robots
        self.assertEqual(robots.networks, 1)
        self.assertEqual(robots.total_logistic_robots, 200)
        self.assertEqual(robots.available_logistic_robots, 120)
        self.assertEqual(robots.total_construction_robots, 60)
        self.assertEqual(robots.available_construction_robots, 30)
        self.assertEqual(robots.robot_limit, 250)
        self.assertEqual(robots.busy_logistic_robots, 80)
        self.assertEqual(robots.busy_construction_robots, 30)

    def test_a_transport_row_is_read(self):
        snapshot = inventory_observation(frame())
        self.assertEqual(len(snapshot.transport), 1)
        wagon = snapshot.transport[0]
        self.assertEqual(wagon.name, "cargo-wagon-1")
        self.assertEqual(wagon.entity_type, "cargo-wagon")
        self.assertEqual(wagon.inventories[0].items[0].count, 400)

    def test_an_unavailable_section_is_unavailable_and_not_empty(self):
        payload = frame()
        payload["logistics"] = {
            "available": False, "status": "unavailable",
            "reason": "no_connected_player_with_character",
        }
        snapshot = inventory_observation(payload)
        self.assertEqual(snapshot.networks_state, UNAVAILABLE)
        self.assertEqual(
            snapshot.networks_reason, "no_connected_player_with_character")
        self.assertEqual(snapshot.networks, ())
        # The other sections are still observed.
        self.assertEqual(snapshot.machines_state, OBSERVED)
        self.assertEqual(snapshot.robots_state, OBSERVED)

    def test_a_missing_section_is_unavailable(self):
        payload = frame()
        del payload["transport"]
        snapshot = inventory_observation(payload)
        self.assertEqual(snapshot.transport_state, UNAVAILABLE)
        self.assertEqual(snapshot.transport, ())

    def test_the_pagination_is_reported(self):
        payload = frame()
        payload["machine_inventories"]["page"] = 2
        payload["machine_inventories"]["page_count"] = 5
        payload["machine_inventories"]["total"] = 70
        payload["logistics"]["page"] = 1
        payload["logistics"]["page_count"] = 2
        snapshot = inventory_observation(payload)
        self.assertEqual(snapshot.machine_page, 2)
        self.assertEqual(snapshot.machine_page_count, 5)
        self.assertEqual(snapshot.machine_total, 70)
        self.assertTrue(snapshot.has_more_machines)
        self.assertTrue(snapshot.has_more_networks)

    def test_the_last_page_reports_no_more_pages(self):
        payload = frame()
        payload["machine_inventories"]["page"] = 5
        payload["machine_inventories"]["page_count"] = 5
        snapshot = inventory_observation(payload)
        self.assertFalse(snapshot.has_more_machines)

    def test_the_snapshot_token_is_reported(self):
        snapshot = inventory_observation(frame())
        self.assertEqual(snapshot.machine_snapshot, "1234:1")
        self.assertEqual(snapshot.logistics_snapshot, "1234:1")

    def test_a_truncated_page_says_so(self):
        payload = frame()
        payload["machine_inventories"]["truncated"] = True
        payload["machine_inventories"]["partial"] = True
        snapshot = inventory_observation(payload)
        self.assertTrue(snapshot.machine_truncated)
        self.assertTrue(snapshot.machine_partial)
        self.assertIn("truncated", snapshot.status_text())

    def test_the_machine_collection_is_bounded(self):
        payload = frame()
        payload["machine_inventories"]["rows"] = [
            machine_row(f"machine-{index}") for index in range(400)
        ]
        snapshot = inventory_observation(payload)
        self.assertLessEqual(len(snapshot.machines), MAX_MACHINE_ROWS)

    def test_the_network_collection_is_bounded(self):
        payload = frame()
        payload["logistics"]["rows"] = [
            network_row(index) for index in range(200)
        ]
        snapshot = inventory_observation(payload)
        self.assertLessEqual(len(snapshot.networks), MAX_NETWORK_ROWS)

    def test_a_malformed_row_is_skipped_not_shown_as_zero(self):
        payload = frame()
        payload["machine_inventories"]["rows"] = [
            {"name": "broken"},
            machine_row(),
        ]
        snapshot = inventory_observation(payload)
        self.assertEqual(len(snapshot.machines), 1)
        self.assertEqual(snapshot.machines[0].name, "assembling-machine-1")

    def test_a_negative_count_is_not_accepted(self):
        payload = frame()
        payload["machine_inventories"]["rows"][0]["inventories"][0]["items"] = [
            {"name": "iron-plate", "count": -5, "quality": "normal"},
        ]
        snapshot = inventory_observation(payload)
        self.assertEqual(snapshot.machines[0].inventories[0].item_count, 0)

    def test_the_snapshot_is_immutable(self):
        snapshot = inventory_observation(frame())
        self.assertIsInstance(snapshot, InventoryObservation)
        with self.assertRaises((AttributeError, TypeError)):
            snapshot.machines = ()  # type: ignore[misc]

    def test_the_status_text_names_the_observed_sections(self):
        snapshot = inventory_observation(frame())
        text = snapshot.status_text()
        self.assertIn("machine rows", text)
        self.assertIn("logistic networks", text)


if __name__ == "__main__":
    unittest.main()
