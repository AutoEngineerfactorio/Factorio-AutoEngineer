"""Regression tests for stable inventory grid layout."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_view import inventory_columns, inventory_fingerprint


class InventoryLayoutTests(unittest.TestCase):
    def test_columns_adapt_to_width(self):
        self.assertEqual(inventory_columns(408), 10)
        self.assertEqual(inventory_columns(248), 6)
        self.assertEqual(inventory_columns(1), 1)

    def test_tick_only_change_does_not_redraw(self):
        before = {"tick": 100, "inventory_available": True, "inventory": [
            {"name": "iron-plate", "count": 12, "quality": "normal"}]}
        after = dict(before, tick=101)
        self.assertEqual(inventory_fingerprint(before, 408), inventory_fingerprint(after, 408))

    def test_slot_change_requires_redraw(self):
        before = {"inventory_available": True, "slots": [
            {"slot": 5, "name": "iron-plate", "count": 12, "quality": "normal"}]}
        after = {"inventory_available": True, "slots": [
            {"slot": 5, "name": "iron-plate", "count": 13, "quality": "normal"}]}
        self.assertNotEqual(inventory_fingerprint(before, 408), inventory_fingerprint(after, 408))

    def test_resize_requires_redraw_when_columns_change(self):
        data = {"inventory_available": True, "inventory": []}
        self.assertNotEqual(inventory_fingerprint(data, 408), inventory_fingerprint(data, 248))

    def test_none_is_accepted(self):
        self.assertIsNone(inventory_fingerprint(None, 410))


if __name__ == "__main__":
    unittest.main()
