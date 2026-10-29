"""Worker and invalidation checks for the production-chain panel."""
import os
import sys
import threading
import time
import unittest
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from test_observed_flow import catalog

try:
    QApplication = import_module("PySide6.QtWidgets").QApplication
    from qt_flow_planner import FlowPlannerWidget, parse_materials
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "Qt unavailable")
class FlowPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def test_editable_inputs_keep_rates_distinct_from_inventory(self):
        self.assertEqual(parse_materials("item:ore = 120"), {"item:ore": 2})
        self.assertEqual(parse_materials("item:seed = 3", 1), {"item:seed": 3})
        with self.assertRaises(ValueError):
            parse_materials("item:ore = 1\nitem:ore = 2")

    def test_solver_runs_off_gui_and_discards_a_stale_catalog_result(self):
        widget = FlowPlannerWidget()
        widget.set_catalog(catalog())
        widget.output.setText("item:plate")
        widget.editors["supplies"].setPlainText("item:ore = 120")
        entered, release = threading.Event(), threading.Event()
        worker_threads = []
        def solve(*args, **kwargs):
            worker_threads.append(threading.get_ident())
            entered.set()
            release.wait(2)
            return {"status": "estimated", "machines": {"make": 1}}
        with patch("qt_flow_planner.solve_observed_flow", side_effect=solve):
            self.assertTrue(widget.calculate())
            self.assertTrue(entered.wait(1))
            self.assertNotEqual(worker_threads, [threading.get_ident()])
            widget.set_catalog(replace(catalog(), state="stale"))
            release.set()
            deadline = time.monotonic() + 3
            while widget._busy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
        self.assertIsNone(widget.last_result)
        self.assertFalse(widget.calculate_button.isEnabled())
        self.assertFalse(widget.calculate())
        widget.close()
        widget.deleteLater()
