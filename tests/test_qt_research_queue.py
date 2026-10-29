"""Offline research queue and observed technology integration checks."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    QApplication = import_module("PySide6.QtWidgets").QApplication
    from qt_catalog import catalog_snapshot
    from qt_research_queue import ResearchPlan, ResearchQueueWidget, observed_technologies
    ENABLED = True
except ImportError:
    ENABLED = False


def snapshot():
    return catalog_snapshot({
        "catalog_status": {"status": "ok", "page": 1, "total": 10},
        "capabilities": {
            "recipes": [{"name": "advanced-gear", "unlock_technologies": [
                {"name": "automation-2", "researched": False}]}],
            "research": ["automation"],
            "machines": [],
            "source_fingerprint": "test-fingerprint",
        },
    })


@unittest.skipUnless(ENABLED, "PySide6 unavailable")
class ResearchQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "plan.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_persistence_dedupe_order_and_removal(self):
        plan = ResearchPlan(self.path)
        self.assertTrue(plan.add("automation-2"))
        self.assertFalse(plan.add("automation-2"))
        self.assertTrue(plan.add("logistics"))
        plan.move(1, -1)
        self.assertEqual(ResearchPlan(self.path).queue, ["logistics", "automation-2"])
        plan.remove(0)
        self.assertEqual(ResearchPlan(self.path).queue, ["automation-2"])

    def test_only_observed_unlock_tech_is_searchable(self):
        techs = observed_technologies(snapshot())
        self.assertIn(("automation", "Researched"), techs)
        self.assertIn(("automation-2", "Not confirmed researched"), techs)
        self.assertNotIn(("made-up-research", "Not confirmed researched"), techs)

    def test_ui_queue_does_not_touch_game(self):
        widget = ResearchQueueWidget(queue_file=self.path)
        try:
            widget.set_snapshot(snapshot())
            self.assertGreaterEqual(widget.available.rowCount(), 2)
            names = [widget.available.item(i, 0).text()
                     for i in range(widget.available.rowCount())]
            widget.available.selectRow(names.index("automation-2"))
            widget.add_selected()
            self.assertEqual(widget.plan.queue, ["automation-2"])
            self.assertEqual(widget.queue_list.count(), 1)
            self.assertIn("Local planning queue", widget.banner.text())
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
