"""Regression tests for the shared inventory and logistics snapshot."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from qt_inventory import (  # noqa: E402
    UNSUPPORTED,
    inventory_snapshot,
    inventory_status_text,
)


def frame(**overrides):
    """Return one synthetic observed view frame."""
    source = {
        "status": "ok",
        "tick": 1000,
        "inventory_available": True,
        "capacity": 80,
        "truncated": False,
        "slots_truncated": False,
        "inventory": [
            {"name": "iron-plate", "quality": "normal", "count": 120},
            {"name": "copper-cable", "quality": "normal", "count": 40},
        ],
    }
    source.update(overrides)
    return source


def telemetry_frame(**overrides):
    """Return one synthetic observed frame with telemetry."""
    source = frame()
    source["telemetry"] = {
        "status": "ok",
        "tick": 1000,
        "production": {
            "status": "ok",
            "items": [{
                "name": "iron-plate",
                "five_seconds": {
                    "produced": 100, "consumed": 20,
                    "per_second_produced": 20.0,
                    "per_second_consumed": 4.0,
                },
            }],
            "fluids": [{
                "name": "water",
                "five_seconds": {
                    "produced": 50, "consumed": 10,
                    "per_second_produced": 10.0,
                    "per_second_consumed": 2.0,
                },
            }],
            "fluid_status": "ok",
            "partial": True,
        },
        "power": {
            "status": "ok",
            "networks": [{
                "network_id": 7,
                "maximum_production": 186000.0,
                "maximum_consumption": 120000.0,
                "consumption_satisfaction": 1.0,
                "production_satisfaction": 0.5,
                "accumulator_energy": 100.0,
                "accumulator_capacity": 200.0,
            }],
        },
    }
    source.update(overrides)
    return source


class InventorySnapshotTests(unittest.TestCase):
    """The snapshot must reflect only what the frame really carried."""

    def test_an_observed_inventory_is_read(self):
        snapshot = inventory_snapshot(frame())
        self.assertTrue(snapshot.inventory_available)
        self.assertEqual(len(snapshot.items), 2)
        self.assertEqual(snapshot.items[0].name, "iron-plate")
        self.assertEqual(snapshot.items[0].count, 120)
        self.assertEqual(snapshot.inventory_capacity, 80)
        self.assertTrue(snapshot.known)

    def test_a_missing_frame_is_unavailable(self):
        snapshot = inventory_snapshot(None)
        self.assertFalse(snapshot.known)
        self.assertEqual(snapshot.items, ())
        self.assertIn("unavailable", inventory_status_text(snapshot).lower())

    def test_an_unavailable_inventory_is_not_an_empty_inventory(self):
        source = frame(inventory_available=False, inventory=[])
        snapshot = inventory_snapshot(source)
        self.assertFalse(snapshot.inventory_available)
        self.assertEqual(snapshot.items, ())

    def test_an_invalid_entry_is_skipped(self):
        source = frame(inventory=[
            {"name": "good", "quality": "normal", "count": 1},
            {"name": "bad-count", "quality": "normal", "count": "many"},
            {"name": "", "quality": "normal", "count": 5},
            "not-a-mapping",
        ])
        snapshot = inventory_snapshot(source)
        self.assertEqual([item.name for item in snapshot.items], ["good"])

    def test_the_quality_is_kept(self):
        source = frame(inventory=[
            {"name": "iron-plate", "quality": "legendary", "count": 1}])
        snapshot = inventory_snapshot(source)
        self.assertEqual(snapshot.items[0].quality, "legendary")
        self.assertIn("legendary", snapshot.items[0].label)

    def test_a_normal_quality_label_is_plain(self):
        source = frame(inventory=[
            {"name": "iron-plate", "quality": "normal", "count": 1}])
        snapshot = inventory_snapshot(source)
        self.assertEqual(snapshot.items[0].label, "iron-plate")

    def test_the_truncation_flags_are_preserved(self):
        source = frame(truncated=True, slots_truncated=True)
        snapshot = inventory_snapshot(source)
        self.assertTrue(snapshot.inventory_truncated)
        self.assertTrue(snapshot.slots_truncated)
        self.assertIn("truncated", inventory_status_text(snapshot).lower())


class ProductionSnapshotTests(unittest.TestCase):
    """The production rows must reflect the game's own statistics."""

    def test_item_production_is_read(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertEqual(len(snapshot.item_production), 1)
        row = snapshot.item_production[0]
        self.assertEqual(row.name, "iron-plate")
        self.assertEqual(row.produced, 100)
        self.assertEqual(row.consumed, 20)
        self.assertEqual(row.produced_per_second, 20.0)
        self.assertEqual(row.consumed_per_second, 4.0)

    def test_fluid_production_is_read(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertEqual(len(snapshot.fluid_production), 1)
        self.assertEqual(snapshot.fluid_production[0].name, "water")
        self.assertEqual(snapshot.fluid_production_status, "ok")

    def test_the_partial_coverage_is_preserved(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertTrue(snapshot.item_production_partial)
        self.assertTrue(snapshot.fluid_production_partial)

    def test_an_unavailable_production_is_not_zero_production(self):
        source = frame()
        source["telemetry"] = {
            "production": {"status": "unavailable", "items": [],
                           "fluid_status": "unavailable", "fluids": []},
        }
        snapshot = inventory_snapshot(source)
        self.assertEqual(snapshot.item_production, ())
        self.assertEqual(snapshot.item_production_status, "unavailable")

    def test_the_electrical_networks_are_read(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertEqual(len(snapshot.networks), 1)
        network = snapshot.networks[0]
        self.assertEqual(network.network_id, 7)
        self.assertEqual(network.maximum_production, 186000.0)
        self.assertEqual(network.consumption_satisfaction, 1.0)
        self.assertEqual(network.accumulator_capacity, 200.0)

    def test_a_network_without_an_id_is_skipped(self):
        source = frame()
        source["telemetry"] = {"power": {"status": "ok", "networks": [
            {"maximum_production": 1.0}]}}
        snapshot = inventory_snapshot(source)
        self.assertEqual(snapshot.networks, ())


class LogisticsSnapshotTests(unittest.TestCase):
    """The logistics rows must reflect the observed roboport cells."""

    def test_the_roboport_cells_are_read(self):
        source = frame(overlays={
            "available": {"logistics": True},
            "logistics": [{
                "x": 10.0, "y": 20.0, "logistic": 8.0,
                "construction": 10.0, "active": True,
            }],
        })
        snapshot = inventory_snapshot(source)
        self.assertTrue(snapshot.logistics_available)
        self.assertEqual(len(snapshot.logistics), 1)
        self.assertEqual(snapshot.logistics[0].logistic_radius, 8.0)
        self.assertTrue(snapshot.logistics[0].active)

    def test_an_unavailable_logistics_layer_has_no_rows(self):
        source = frame(overlays={
            "available": {"logistics": False},
            "logistics": [],
        })
        snapshot = inventory_snapshot(source)
        self.assertFalse(snapshot.logistics_available)
        self.assertEqual(snapshot.logistics, ())

    def test_an_incomplete_logistics_row_is_skipped(self):
        source = frame(overlays={
            "available": {"logistics": True},
            "logistics": [{"x": 10.0, "y": 20.0}],
        })
        snapshot = inventory_snapshot(source)
        self.assertEqual(snapshot.logistics, ())


class UnsupportedFieldTests(unittest.TestCase):
    """The gaps of the observation protocol must be explicit."""

    def test_machine_inventories_are_explicitly_unsupported(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertFalse(snapshot.machine_inventories_supported)
        self.assertEqual(snapshot.machine_inventories_reason, UNSUPPORTED)

    def test_logistic_network_contents_are_explicitly_unsupported(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertFalse(snapshot.logistic_network_contents_supported)
        self.assertEqual(
            snapshot.logistic_network_contents_reason, UNSUPPORTED)

    def test_robot_counts_are_explicitly_unsupported(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertFalse(snapshot.robot_counts_supported)
        self.assertEqual(snapshot.robot_counts_reason, UNSUPPORTED)

    def test_transport_and_storage_are_explicitly_unsupported(self):
        snapshot = inventory_snapshot(telemetry_frame())
        self.assertFalse(snapshot.transport_storage_supported)
        self.assertEqual(snapshot.transport_storage_reason, UNSUPPORTED)


class StateTests(unittest.TestCase):
    """The truthfulness state must survive the snapshot."""

    def test_a_stale_frame_keeps_its_rows_and_is_marked_stale(self):
        snapshot = inventory_snapshot(frame(), state="stale")
        self.assertEqual(snapshot.state, "stale")
        self.assertEqual(len(snapshot.items), 2)
        self.assertIn("stale", inventory_status_text(snapshot).lower())

    def test_a_frame_with_nothing_observed_is_unavailable(self):
        source = {"status": "ok", "tick": 1}
        snapshot = inventory_snapshot(source)
        self.assertFalse(snapshot.known)


if __name__ == "__main__":
    unittest.main()
