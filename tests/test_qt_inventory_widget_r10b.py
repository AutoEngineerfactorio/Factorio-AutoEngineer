"""Offline regression tests for the R10-B Qt inventory and logistics widget.

The widget renders the observed snapshot and must never show a value the
game did not report. The tests pin:

* the observed machine, network, robot and transport rows are rendered;
* an unobserved section is shown as **Unavailable**, never as zero;
* the search filter hides the rows that do not match;
* **Load more** is enabled only when the game reported more pages.

The tests run on the offscreen Qt platform, so they need no display.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

try:
    from importlib import import_module

    qt_widgets = import_module("PySide6.QtWidgets")
except ImportError:
    raise unittest.SkipTest("PySide6 is not installed")

QApplication = qt_widgets.QApplication

from qt_inventory_observations import inventory_observation  # noqa: E402,F401

_APP = None


def app() -> QApplication:
    """Return the shared Qt application."""
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def machine_row(name: str = "assembling-machine-1",
                entity_type: str = "assembling-machine",
                surface: str = "nauvis") -> dict:
    """Return one observed machine row."""
    return {
        "name": name,
        "type": entity_type,
        "surface": surface,
        "quality": "normal",
        "x": 10,
        "y": -20,
        "active": True,
        "recipe": "iron-gear-wheel",
        "inventories": [{
            "category": "ingredient",
            "identifier": "chest",
            "capacity": 4,
            "items": [
                {"name": "iron-plate", "count": 100, "quality": "normal"},
                {"name": "copper-plate", "count": 50, "quality": "rare"},
            ],
            "empty": False,
            "truncated": False,
        }],
        "fluids": [],
    }


def network_row(network_id: int = 1, surface: str = "nauvis") -> dict:
    """Return one observed logistic network row."""
    return {
        "network_id": network_id,
        "surface": surface,
        "force": "player",
        "custom_name": "main",
        "available_logistic_robots": 120,
        "all_logistic_robots": 200,
        "available_construction_robots": 30,
        "all_construction_robots": 60,
        "robot_limit": 250,
        "items": [{"name": "iron-plate", "count": 5000, "quality": "normal"}],
        "providers": ["provider-chest"],
        "requesters": ["requester-chest"],
        "storages": ["storage-chest"],
        "items_truncated": False,
    }


def frame(**sections) -> dict:
    """Return one ``autoengineer_inventory`` frame."""
    payload = {
        "status": "ok",
        "protocol": 1,
        "tick": 1234,
        "surface": "nauvis",
        "machine_inventories": {
            "available": True, "status": "ok",
            "page": 1, "page_size": 16, "total": 1, "page_count": 1,
            "matched": 1, "partial": False, "truncated": False,
            "snapshot": "1234:1",
            "rows": [machine_row()],
        },
        "logistics": {
            "available": True, "status": "ok",
            "page": 1, "page_size": 16, "total": 1, "page_count": 1,
            "snapshot": "1234:1",
            "rows": [network_row()],
        },
        "robots": {
            "available": True, "status": "ok", "networks": 1,
            "total_logistic_robots": 200, "available_logistic_robots": 120,
            "total_construction_robots": 60,
            "available_construction_robots": 30,
            "robot_limit": 250, "partial": False,
        },
        "transport": {
            "available": True, "status": "ok",
            "page": 1, "page_size": 16, "total": 1, "page_count": 1,
            "matched": 1,
            "rows": [{
                "name": "cargo-wagon-1", "type": "cargo-wagon",
                "surface": "nauvis", "quality": "normal", "x": 3, "y": 3,
                "inventories": [{
                    "category": "ingredient", "identifier": "cargo_wagon",
                    "capacity": 8,
                    "items": [{"name": "iron-plate", "count": 400,
                               "quality": "normal"}],
                    "empty": False, "truncated": False,
                }],
                "fluids": [],
            }],
        },
    }
    payload.update(sections)
    return payload


class InventoryWidgetTests(unittest.TestCase):
    """The widget must render the observed data and nothing else."""

    def setUp(self):
        app()
        from qt_inventory_widget import InventoryWidget
        self.widget_class = InventoryWidget

    def test_the_inventory_scope_shows_the_machine_rows(self):
        widget = self.widget_class(scope="inventory")
        widget.set_observation(frame())
        self.assertEqual(widget.machine_table.rowCount(), 1)
        self.assertEqual(widget.machine_table.item(0, 0).text(),
                         "assembling-machine-1")
        self.assertEqual(widget.machine_table.item(0, 1).text(),
                         "assembling-machine")
        self.assertEqual(widget.machine_table.item(0, 3).text(), "nauvis")
        self.assertIn("iron-plate", widget.machine_table.item(0, 5).text())
        self.assertIn("rare", widget.machine_table.item(0, 6).text())
        self.assertEqual(widget.machine_table.item(0, 7).text(), "4")

    def test_the_inventory_scope_keeps_the_player_inventory_tab(self):
        widget = self.widget_class(scope="inventory")
        titles = [widget.tabs.tabText(index)
                  for index in range(widget.tabs.count())]
        self.assertIn("Machines", titles)
        self.assertIn("Player inventory", titles)

    def test_the_logistics_scope_shows_the_network_rows(self):
        widget = self.widget_class(scope="logistics")
        widget.set_observation(frame())
        self.assertEqual(widget.logistic_network_table.rowCount(), 1)
        self.assertIn("main", widget.logistic_network_table.item(0, 0).text())
        self.assertIn("iron-plate",
                      widget.logistic_network_table.item(0, 2).text())
        self.assertEqual(widget.logistic_network_table.item(0, 3).text(),
                         "provider-chest")

    def test_the_logistics_scope_shows_the_robot_rows(self):
        widget = self.widget_class(scope="logistics")
        widget.set_observation(frame())
        names = [widget.robot_table.item(index, 0).text()
                 for index in range(widget.robot_table.rowCount())]
        values = [widget.robot_table.item(index, 1).text()
                  for index in range(widget.robot_table.rowCount())]
        self.assertIn("Logistic robots available", names)
        self.assertIn("Construction robots busy", names)
        self.assertEqual(values[names.index("Logistic robots available")],
                         "120")
        self.assertEqual(values[names.index("Logistic robots busy")], "80")

    def test_the_logistics_scope_shows_the_transport_rows(self):
        widget = self.widget_class(scope="logistics")
        widget.set_observation(frame())
        self.assertEqual(widget.transport_table.rowCount(), 1)
        self.assertEqual(widget.transport_table.item(0, 0).text(),
                         "cargo-wagon-1")
        self.assertIn("iron-plate", widget.transport_table.item(0, 4).text())

    def test_an_unobserved_section_is_unavailable_and_not_zero(self):
        payload = frame()
        payload["robots"] = {
            "available": False, "status": "unavailable",
            "reason": "no_connected_player_with_character",
        }
        widget = self.widget_class(scope="logistics")
        widget.set_observation(payload)
        names = [widget.robot_table.item(index, 0).text()
                 for index in range(widget.robot_table.rowCount())]
        values = [widget.robot_table.item(index, 1).text()
                  for index in range(widget.robot_table.rowCount())]
        self.assertEqual(values[names.index("Logistic robots available")],
                         "—")
        self.assertIn("Unavailable", widget.unsupported.text())
        self.assertIn("Robot counts", widget.unsupported.text())

    def test_an_absent_frame_is_unavailable(self):
        widget = self.widget_class(scope="inventory")
        widget.set_frame(None)
        self.assertEqual(widget.machine_table.rowCount(), 0)
        self.assertIn("Unavailable", widget.unsupported.text())

    def test_the_search_filter_hides_the_rows_that_do_not_match(self):
        payload = frame()
        payload["machine_inventories"]["rows"] = [
            machine_row("assembling-machine-1"),
            machine_row("chemical-plant-1", "assembling-machine"),
        ]
        widget = self.widget_class(scope="inventory")
        widget.set_observation(payload)
        self.assertEqual(widget.visible_machine_rows, 2)
        widget.search.setText("chemical")
        self.assertEqual(widget.visible_machine_rows, 1)

    def test_the_search_filter_can_be_cleared(self):
        widget = self.widget_class(scope="inventory")
        widget.set_observation(frame())
        widget.search.setText("iron-plate")
        self.assertEqual(widget.visible_machine_rows, 1)
        widget.search.setText("")
        self.assertEqual(widget.visible_machine_rows, 1)

    def test_the_filter_does_not_change_the_observed_counts(self):
        widget = self.widget_class(scope="inventory")
        widget.set_observation(frame())
        widget.search.setText("nothing-matches-this")
        self.assertEqual(widget.visible_machine_rows, 0)
        snapshot = widget.snapshot
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(len(snapshot.machines), 1)

    def test_load_more_is_disabled_when_there_is_no_further_page(self):
        widget = self.widget_class(scope="inventory")
        widget.set_observation(frame())
        self.assertFalse(widget.load_more_button.isEnabled())

    def test_load_more_is_enabled_when_the_game_reported_more_pages(self):
        payload = frame()
        payload["machine_inventories"]["page"] = 1
        payload["machine_inventories"]["page_count"] = 3
        widget = self.widget_class(scope="inventory")
        widget.set_observation(payload)
        self.assertTrue(widget.load_more_button.isEnabled())

    def test_the_refresh_button_emits_the_refresh_request(self):
        widget = self.widget_class(scope="inventory")
        seen: list[bool] = []
        widget.refreshRequested.connect(lambda: seen.append(True))
        widget.refresh_button.click()
        self.assertEqual(seen, [True])

    def test_the_load_more_button_emits_the_load_more_request(self):
        payload = frame()
        payload["machine_inventories"]["page_count"] = 3
        widget = self.widget_class(scope="inventory")
        widget.set_observation(payload)
        seen: list[bool] = []
        widget.loadMoreRequested.connect(lambda: seen.append(True))
        widget.load_more_button.click()
        self.assertEqual(seen, [True])

    def test_a_disabled_load_more_button_does_not_emit(self):
        """Without a further page the button must do nothing."""
        widget = self.widget_class(scope="inventory")
        widget.set_observation(frame())
        seen: list[bool] = []
        widget.loadMoreRequested.connect(lambda: seen.append(True))
        widget.load_more_button.click()
        self.assertEqual(seen, [])

    def test_the_status_line_names_the_observed_sections(self):
        widget = self.widget_class(scope="inventory")
        widget.set_observation(frame())
        self.assertIn("machine rows", widget.status.text())
        self.assertIn("logistic networks", widget.status.text())


if __name__ == "__main__":
    unittest.main()
