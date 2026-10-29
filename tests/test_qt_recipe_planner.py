"""Observed recipe production planner UI regressions."""
from __future__ import annotations

import os
import sys
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    QApplication = import_module("PySide6.QtWidgets").QApplication
    from qt_catalog import catalog_snapshot
    from qt_recipe_planner import RecipePlannerWidget, compatible_machines
    ENABLED = True
except ImportError:
    ENABLED = False


def snapshot():
    return catalog_snapshot({
        "catalog_status": {"status": "assembled", "total_count": 1, "page": 1, "total_pages": 1},
        "capabilities": {
            "recipes": [{
                "name": "iron-gear-wheel", "enabled": True, "hidden": False,
                "category": "crafting", "categories": ["crafting"],
                "crafting_time": 0.5,
                "ingredients": [{"name": "iron-plate", "type": "item", "amount": 2}],
                "products": [{"name": "iron-gear-wheel", "type": "item", "amount": 1,
                              "deterministic": True}],
            }],
            "machines": [{"name": "assembling-machine-2",
                          "crafting_categories": ["crafting"],
                          "crafting_speed": 0.75, "energy_usage": 150000}],
            "research": [],
            "source_fingerprint": "observed-fixture",
            "game_version": "2.1.23",
        },
    })


@unittest.skipUnless(ENABLED, "PySide6 unavailable")
class RecipePlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = RecipePlannerWidget()
        self.widget.set_snapshot(snapshot())

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def test_only_observed_compatible_machines_are_used(self):
        self.assertEqual(len(compatible_machines(
            {"category": "crafting"},
            tuple(snapshot().machines))), 1)
        self.assertEqual(compatible_machines(
            {"category": "chemistry"}, tuple(snapshot().machines)), [])

    def test_rate_calculation_uses_observed_recipe_and_machine(self):
        self.widget.catalog.recipe_table.selectRow(0)
        result = self.widget.calculate()
        assert result is not None
        self.assertEqual(result["machine_count"], 1)
        self.assertEqual(result["machine"]["name"], "assembling-machine-2")
        self.assertEqual(result["recipe"]["name"], "iron-gear-wheel")
        self.assertTrue(self.widget.create_blueprint_button.isEnabled())
        self.assertIn("Power", self.widget.summary.text())

    def test_plan_is_forwarded_for_blueprint_generation(self):
        output = []
        self.widget.planReady.connect(output.append)
        self.widget.catalog.recipe_table.selectRow(0)
        self.widget.send_plan()
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["recipe"]["name"], "iron-gear-wheel")

    def test_incompatible_machine_stays_unavailable(self):
        source = snapshot()
        widget = self.widget
        payload = {
            "catalog_status": {"status": "assembled", "total_count": 1},
            "capabilities": {
                "recipes": list(source.recipes), "machines": [],
                "research": [], "source_fingerprint": "other",
            },
        }
        widget.catalog.set_frame(payload)
        widget.catalog.recipe_table.selectRow(0)
        widget.calculate()
        self.assertFalse(widget.create_blueprint_button.isEnabled())
        self.assertIn("unknown", widget.summary.text().lower())

    def test_stale_catalog_cannot_forward_a_previous_plan(self):
        from dataclasses import replace
        self.widget.catalog.recipe_table.selectRow(0)
        self.widget.calculate()
        output=[]
        self.widget.planReady.connect(output.append)
        self.widget.catalog.set_snapshot(replace(snapshot(),state="stale"))
        self.widget.send_plan()
        self.assertEqual(output,[])
        self.assertFalse(self.widget.create_blueprint_button.isEnabled())
        self.assertIsNone(self.widget.last_plan)


if __name__ == "__main__":
    unittest.main()
