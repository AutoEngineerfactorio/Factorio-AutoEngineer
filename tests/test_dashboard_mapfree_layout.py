"""Map-free dashboard preserves interfaces without instantiating a map canvas."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import autoengineer_dashboard as dashboard


class MapFreeViewTests(unittest.TestCase):
    def test_map_updates_never_request_chunks(self):
        stub = Mock()
        stub.available = False
        stub.message = Mock()
        dashboard.MapFreeStatusView.update_frame(stub, {
            "status": "ok", "surface": "nauvis", "tick": 12
        })
        self.assertTrue(stub.available)
        self.assertEqual(stub.last["tick"], 12)
        self.assertIsNone(dashboard.MapFreeStatusView.request_viewport(stub))

    def test_unavailable_readings_are_not_misrepresented_as_live(self):
        stub = Mock()
        stub.available = True
        stub.message = Mock()
        dashboard.MapFreeStatusView.update_frame(stub, {"status": "unavailable"})
        self.assertFalse(stub.available)

    def test_partial_multitick_catalog_is_displayed_without_claiming_complete(self):
        import json

        from tests.test_catalog_assembly import page
        raw = page(1, ["gear"], fingerprint=None, truncated=True,
                   total_count=2, total_pages=2)
        raw["catalog_status"]["status"] = "assembled"
        raw["catalog_status"]["pages_collected"] = 2
        stub = Mock()
        stub.planning_session.observe.return_value = {
            "planner_ready": False, "reason": "partial catalog"
        }
        dashboard.Dashboard.display_catalog_frame(
            stub, dashboard.PREFIX + json.dumps({"schema": 1, **raw}))
        stub.planning_session.observe.assert_called_once()
        self.assertTrue(stub.planning_session.observe.call_args.args[0]
                        ["capabilities"]["truncated"])
        # Proven source field is partial even if the original mock contains
        # manually supplied rows; dashboard must not enable planning.
        self.assertEqual(stub.planning_view.update_intelligence.call_count, 1)

    def test_legacy_stop_stubs_do_not_require_catalog_observer(self):
        from inspect import getsource
        self.assertIn('getattr(self, "catalog_observer", None)',
                      getsource(dashboard.Dashboard.close_display))
        self.assertIn('getattr(self, "catalog_observer", None)',
                      getsource(dashboard.Dashboard.process_events))

    def test_catalog_and_telemetry_are_separate_processes(self):
        from inspect import getsource
        catalog = getsource(dashboard.Dashboard.start_catalog_observer)
        self.assertIn('AUTOENGINEER_CATALOG_ONLY', catalog)
        self.assertIn('AUTOENGINEER_CATALOG_FULL', catalog)
        self.assertIn('dashboard_observer', catalog)
        self.assertNotIn('AUTOENGINEER_ENABLE_LIVE_MAP', catalog)
        self.assertIn('self.planning_session.observe(frame)',
                      getsource(dashboard.Dashboard.display_catalog_frame))
        self.assertNotIn('telemetry_view',
                         getsource(dashboard.Dashboard.display_catalog_frame))

    def test_dashboard_creates_no_live_map_canvas(self):
        from inspect import getsource
        source = getsource(dashboard.Dashboard.build_ui)
        self.assertNotIn("LiveView(", source)
        self.assertIn("MapFreeStatusView(tabs)", source)
        self.assertLess(source.index('text="RECIPES & RESEARCH"'),
                        source.index('text="FACTORY OVERVIEW"'))


if __name__ == "__main__":
    unittest.main()
