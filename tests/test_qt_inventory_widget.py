"""Regression tests for the Qt inventory and logistics workspace."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication
    import qt_inventory_widget

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


def frame():
    """Return one synthetic observed view frame with telemetry."""
    return {
        "status": "ok",
        "tick": 1000,
        "inventory_available": True,
        "capacity": 80,
        "truncated": False,
        "slots_truncated": False,
        "inventory": [
            {"name": "iron-plate", "quality": "normal", "count": 120},
            {"name": "copper-cable", "quality": "legendary", "count": 40},
        ],
        "telemetry": {
            "status": "ok",
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
        },
        "overlays": {
            "available": {"logistics": True},
            "logistics": [{
                "x": 10.0, "y": 20.0, "logistic": 8.0,
                "construction": 10.0, "active": True,
            }],
        },
    }


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class InventoryWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_inventory_widget.InventoryWidget(scope="inventory")

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def test_the_player_inventory_is_rendered(self):
        self.widget.set_frame(frame())
        self.assertEqual(self.widget.inventory_table.rowCount(), 2)
        self.assertEqual(
            self.widget.inventory_table.item(0, 0).text(), "iron-plate")
        self.assertEqual(self.widget.inventory_table.item(0, 2).text(), "120")

    def test_the_quality_is_shown_in_the_label(self):
        self.widget.set_frame(frame())
        self.assertEqual(
            self.widget.inventory_table.item(1, 0).text(),
            "copper-cable (legendary)")

    def test_the_production_rows_are_rendered(self):
        self.widget.set_frame(frame())
        self.assertEqual(self.widget.production_table.rowCount(), 2)
        self.assertEqual(
            self.widget.production_table.item(0, 0).text(), "iron-plate")
        self.assertEqual(self.widget.production_table.item(0, 3).text(), "20.00")
        self.assertEqual(
            self.widget.production_table.item(1, 0).text(), "water")

    def test_the_electrical_networks_are_rendered(self):
        self.widget.set_frame(frame())
        self.assertEqual(self.widget.network_table.rowCount(), 1)
        self.assertEqual(self.widget.network_table.item(0, 0).text(), "7")
        self.assertEqual(
            self.widget.network_table.item(0, 3).text(), "100.0%")

    def test_the_unsupported_fields_are_named(self):
        self.widget.set_frame(frame())
        text = self.widget.unsupported.text()
        # R10-B renamed these sections when the observations that used to
        # be missing were implemented. The view frame carries none of the
        # four R10-B sections, so all four are still named as unavailable.
        self.assertIn("Machine inventories", text)
        self.assertIn("Logistic networks", text)
        self.assertIn("Robot counts", text)
        self.assertIn("Transport and storage", text)
        self.assertIn("Unavailable", text)

    def test_a_missing_frame_is_not_rendered_as_empty_data(self):
        self.widget.set_frame(None)
        self.assertEqual(self.widget.inventory_table.rowCount(), 0)
        self.assertEqual(self.widget.production_table.rowCount(), 0)
        self.assertIn("unavailable", self.widget.status.text().lower())

    def test_an_unknown_number_is_an_em_dash_not_a_zero(self):
        source = frame()
        source["telemetry"]["power"]["networks"] = [{
            "network_id": 3,
        }]
        self.widget.set_frame(source)
        self.assertEqual(
            self.widget.network_table.item(0, 1).text(),
            qt_inventory_widget.UNKNOWN)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class LogisticsWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_inventory_widget.InventoryWidget(scope="logistics")

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def test_the_roboport_cells_are_rendered(self):
        self.widget.set_frame(frame())
        self.assertEqual(self.widget.logistics_table.rowCount(), 1)
        self.assertEqual(
            self.widget.logistics_table.item(0, 0).text(), "(10, 20)")
        self.assertEqual(
            self.widget.logistics_table.item(0, 3).text(), "Yes")

    def test_an_inactive_roboport_is_shown_as_inactive(self):
        source = frame()
        source["overlays"]["logistics"][0]["active"] = False
        self.widget.set_frame(source)
        self.assertEqual(
            self.widget.logistics_table.item(0, 3).text(), "No")

    def test_the_unsupported_logistics_fields_are_named(self):
        self.widget.set_frame(frame())
        text = self.widget.unsupported.text()
        # R10-B renamed the sections when the observations were implemented.
        self.assertIn("Logistic networks", text)
        self.assertIn("Robot counts", text)
        self.assertIn("Transport and storage", text)

    def test_an_unknown_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            qt_inventory_widget.InventoryWidget(scope="unknown")


if __name__ == "__main__":
    unittest.main()
