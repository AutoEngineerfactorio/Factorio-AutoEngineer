"""Tests for the Factorio-style inventory rendering in the dashboard view."""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import tkinter as tk

from dashboard_inventory import SLOT_SIZE
from dashboard_view import LiveView


def observed(slots, capacity, **extra):
    data = {
        "slots": slots,
        "capacity": capacity,
        "inventory_available": True,
        "truncated": False,
        "slots_truncated": False,
    }
    data.update(extra)
    return data


class InventoryViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.view = LiveView(self.root)
        self.view.items.configure(width=410, height=400)
        # A withdrawn widget reports a width of 1; pin the layout width so the
        # column count is deterministic and independent of the window manager.
        self.view.items.winfo_width = lambda: 410

    def render(self, data):
        self.view.last = data
        self.view.inventory()

    def test_slots_are_drawn_for_every_capacity_position(self):
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=10))
        self.assertEqual(len(self.view.slot_nodes), 10)

    def test_empty_slots_stay_visible(self):
        self.render(observed([
            {"slot": 2, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=6))
        self.assertIn(1, self.view.slot_nodes)
        self.assertIn(2, self.view.slot_nodes)
        self.assertIn(6, self.view.slot_nodes)

    def test_only_changed_slots_are_redrawn(self):
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 2, "name": "copper-plate", "quality": "normal", "count": 3},
        ], capacity=4))
        before = dict(self.view.slot_nodes)
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 2, "name": "copper-plate", "quality": "normal", "count": 4},
        ], capacity=4))
        # Slot 1 keeps exactly the same canvas items: it was not redrawn.
        self.assertEqual(before[1], self.view.slot_nodes[1])
        self.assertNotEqual(before[2], self.view.slot_nodes[2])

    def test_scroll_position_survives_an_update(self):
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=80))
        self.view.items.yview_moveto(0.5)
        before = self.view.items.yview()
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 6},
        ], capacity=80))
        self.assertEqual(self.view.items.yview(), before)

    def test_removed_item_returns_the_slot_to_empty(self):
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=4))
        self.render(observed([], capacity=4))
        self.assertIn(1, self.view.slot_nodes)
        hint = self.view.slot_hits[1][2]
        self.assertIn("empty", hint)

    def test_aggregate_fallback_is_labelled(self):
        self.view.last = {
            "inventory": [{"name": "iron-plate", "quality": "normal", "count": 9}],
            "inventory_available": True,
            "truncated": False,
        }
        self.view.inventory()
        self.assertIn("aggregate", self.view.inventory_status.get())

    def test_unavailable_inventory_clears_the_grid(self):
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=4))
        self.render({"inventory_available": False, "truncated": False})
        self.assertEqual(self.view.slot_nodes, {})
        self.assertIn("unavailable", self.view.inventory_status.get())

    def test_tooltip_reports_slot_item_count_and_quality(self):
        self.render(observed([
            {"slot": 3, "name": "iron-plate", "quality": "rare", "count": 12},
        ], capacity=6))
        hint = self.view.slot_hits[3][2]
        self.assertIn("Slot 3", hint)
        self.assertIn("iron-plate", hint)
        self.assertIn("12", hint)
        self.assertIn("rare", hint)

    def test_quality_slot_draws_more_items_than_a_normal_slot(self):
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 2, "name": "iron-plate", "quality": "epic", "count": 5},
        ], capacity=4))
        self.assertGreater(
            len(self.view.slot_nodes[2]), len(self.view.slot_nodes[1])
        )

    def test_slot_positions_follow_the_grid(self):
        self.render(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 11, "name": "copper-plate", "quality": "normal", "count": 5},
        ], capacity=20))
        first = self.view.slot_hits[1]
        eleventh = self.view.slot_hits[11]
        self.assertEqual(first[0], 4)
        self.assertEqual(first[1], 4)
        self.assertEqual(eleventh[0], 4)
        self.assertEqual(eleventh[1], first[1] + SLOT_SIZE)


class InventoryFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.view = LiveView(self.root)
        self.view.items.winfo_width = lambda: 410

    def test_disconnected_observer_marks_the_inventory_stale(self):
        self.view.last = {
            "slots": [{"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5}],
            "capacity": 4,
            "inventory_available": True,
            "truncated": False,
            "slots_truncated": False,
        }
        self.view.available = False
        self.view.inventory()
        self.assertIn("STALE", self.view.inventory_status.get())

    def test_old_reading_marks_the_inventory_stale(self):
        self.view.last = {
            "slots": [{"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5}],
            "capacity": 4,
            "inventory_available": True,
            "truncated": False,
            "slots_truncated": False,
        }
        self.view.available = True
        self.view.received = time.monotonic() - 30
        self.view.inventory()
        self.assertIn("STALE", self.view.inventory_status.get())

    def test_fresh_reading_is_not_marked_stale(self):
        self.view.last = {
            "slots": [{"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5}],
            "capacity": 4,
            "inventory_available": True,
            "truncated": False,
            "slots_truncated": False,
        }
        self.view.available = True
        self.view.received = time.monotonic()
        self.view.inventory()
        self.assertNotIn("STALE", self.view.inventory_status.get())


class RealFactorioIconTests(unittest.TestCase):
    """The icons must come from the verified isolated 2.1.23 installation."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.view = LiveView(self.root)
        self.view.items.winfo_width = lambda: 410

    def test_vanilla_item_icon_is_loaded(self):
        image = self.view.icon("iron-plate")
        self.assertIsNotNone(image, "iron-plate icon missing from the 2.1.23 install")
        assert image is not None
        self.assertEqual(image.width(), 32)
        self.assertEqual(image.height(), 32)

    def test_space_age_item_icon_is_loaded(self):
        image = self.view.icon("advanced-thruster-fuel")
        self.assertIsNotNone(image, "Space Age icon missing from the 2.1.23 install")

    def test_quality_badge_icon_is_loaded(self):
        image = self.view.quality_badge("epic")
        self.assertIsNotNone(image, "epic quality badge missing")

    def test_missing_icon_returns_none_without_raising(self):
        self.assertIsNone(self.view.icon("definitely-not-an-item-xyz"))

    def test_unsafe_name_returns_none(self):
        self.assertIsNone(self.view.icon("../secret"))


if __name__ == "__main__":
    unittest.main()
