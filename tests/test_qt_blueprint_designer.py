"""Observed recipe to generated exchange string, end-to-end in Qt."""
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
    from blueprint_document import decode
    from qt_blueprint_designer import BlueprintDesigner
    from qt_catalog import catalog_snapshot
    ENABLED = True
except ImportError:
    ENABLED = False


def frame():
    return catalog_snapshot({
        "catalog_status": {"status": "assembled", "total_count": 1, "total_pages": 1},
        "capabilities": {
            "source_fingerprint": "observed-fp",
            "game_version": "2.1.23",
            "recipes": [{"name": "iron-gear-wheel", "enabled": True,
                         "category": "crafting", "categories": ["crafting"],
                         "crafting_time": 0.5,
                         "ingredients": [{"name": "iron-plate", "type": "item", "amount": 2}],
                         "products": [{"name": "iron-gear-wheel", "type": "item",
                                      "amount": 1, "deterministic": True}]}],
            "machines": [{"name": "assembling-machine-2",
                          "crafting_categories": ["crafting"],
                          "crafting_speed": 0.75, "energy_usage": 150000}],
            "research": ["automation"],
        },
    })


@unittest.skipUnless(ENABLED, "PySide6 unavailable")
class BlueprintDesignerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = BlueprintDesigner()
        self.widget.set_snapshot(frame())

    def tearDown(self):
        self.widget.close()

    def test_user_target_creates_real_exportable_layout(self):
        received = []
        self.widget.generated.connect(received.append)
        self.widget.search.setText("iron-gear")
        self.assertEqual(self.widget.recipe.count(), 1)
        result = self.widget.generate()
        assert result is not None
        self.assertEqual(len(received), 1)
        entities = decode(result["exchange"])["blueprint"]["entities"]
        self.assertEqual(len(entities), 2)
        self.assertTrue(all(x["name"] == "assembling-machine-2" for x in entities))
        self.assertIn("NOT buildability verified", self.widget.status.text())

    def test_unobserved_recipe_is_not_available(self):
        self.widget.search.setText("no-such-custom-machine")
        self.assertFalse(self.widget.generate_button.isEnabled())
        self.assertIsNone(self.widget.generate())


if __name__ == "__main__":
    unittest.main()
