"""Read-only map expansion control tests without requiring a display."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_view import LiveView


class LayoutControlTests(unittest.TestCase):
    def test_map_expand_hides_and_restores_inventory(self):
        view = Mock()
        view.map_expanded = False
        view.inventory_pane = object()
        LiveView.toggle_map_expanded(view)
        self.assertTrue(view.map_expanded)
        view.map_inventory_panes.forget.assert_called_once_with(view.inventory_pane)
        view.expand_button.configure.assert_called_with(text="Show inventory")
        view.draw.assert_called_once()

        LiveView.toggle_map_expanded(view)
        self.assertFalse(view.map_expanded)
        view.map_inventory_panes.add.assert_called_once_with(view.inventory_pane, weight=1)
        view.expand_button.configure.assert_called_with(text="Expand map")
        self.assertEqual(view.draw.call_count, 2)


if __name__ == "__main__":
    unittest.main()
