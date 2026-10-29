"""Ensure telemetry-only frames do not force a complete Tk map redraw."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_view import LiveView


class _View:
    update_frame = LiveView.update_frame
    schedule_map_redraw = LiveView.schedule_map_redraw
    flush_map_redraw = LiveView.flush_map_redraw

    def __init__(self):
        self.last = None
        self.offset = {"x": 0, "y": 0}
        self.overlay_entries = {}
        self.inventory = Mock()
        self.draw = Mock()
        self.after = Mock()
        self._map_draw_at = 0.0
        self._map_draw_pending = False


class RedrawTests(unittest.TestCase):
    def frame(self, tick, resources=None):
        return {"status": "ok", "surface": "nauvis", "tick": tick,
                "position": {"x": 0.0, "y": 0.0},
                "terrain": {"tiles": []}, "map": {"entities": resources or []}}

    def test_tick_only_change_does_not_redraw(self):
        view = _View()
        view.update_frame(self.frame(1))
        view.update_frame(self.frame(2))
        self.assertEqual(view.draw.call_count, 1)
        self.assertEqual(view.inventory.call_count, 2)
        assert view.last is not None
        self.assertEqual(view.last["tick"], 2)

    def test_cache_hit_counters_do_not_redraw(self):
        view = _View()
        old = self.frame(1)
        old["map"]["stats"] = {"hits": 4}
        view.update_frame(old)
        newer = self.frame(2)
        newer["map"]["stats"] = {"hits": 100}
        view.update_frame(newer)
        self.assertEqual(view.draw.call_count, 1)

    def test_new_observed_ore_is_rendered_after_debounce(self):
        view = _View()
        view.update_frame(self.frame(1))
        view.update_frame(self.frame(2, [{"kind": "resource", "x": 1, "y": 2}]))
        self.assertEqual(view.draw.call_count, 1)
        view.after.assert_called_once()
        view.flush_map_redraw()
        self.assertEqual(view.draw.call_count, 2)

    def test_many_frames_schedule_only_one_pending_draw(self):
        view = _View()
        view.update_frame(self.frame(1))
        for n in range(2, 20):
            view.update_frame(self.frame(n, [{"kind": "resource", "x": n, "y": 2}]))
        self.assertEqual(view.draw.call_count, 1)
        view.after.assert_called_once()
        view.flush_map_redraw()
        self.assertEqual(view.draw.call_count, 2)
        assert view.last is not None
        self.assertEqual(view.last["tick"], 19)


if __name__ == "__main__":
    unittest.main()
