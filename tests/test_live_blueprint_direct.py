"""Contract checks for constructing exact decoded pY print on disposable surface."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from live_blueprint_direct import source_layout  # noqa: E402

BLUEPRINT = ROOT / ".local/blueprint-stress/py-oxygen-nitrogen-source.txt"


class BlueprintDirectTests(unittest.TestCase):
    def test_blueprint_layout_is_transferred_without_changing_entity_count(self):
        import json

        details, payload = source_layout(BLUEPRINT)
        obj = json.loads(payload)
        self.assertEqual(details["original_entity_count"], 1225)
        self.assertEqual(len(obj["items"]), 1225)
        self.assertIn("distilator", obj["names"])
        self.assertIn("purest-nitrogen-gas", obj["recipes"])
        self.assertEqual(len(obj["items"][0]), 5)

    def test_only_creative_test_surface_and_exact_names_are_created(self):
        text = (ROOT / "tests/live_blueprint_direct.py").read_text(encoding="utf-8")
        self.assertIn("ae-py-blueprint-stress", text)
        self.assertIn("s.create_entity(o)", text)
        self.assertIn("helpers.json_to_table", text)
        self.assertIn("recipes_set", text)
        self.assertIn("AE_DIRECT_GATE_READY", text)
        self.assertIn("AE_BP_STATE", text)
        self.assertIn("substation", text)
        self.assertNotIn("/silent-command", text)
        stress = (ROOT / "tests/live_long_stress.py").read_text(encoding="utf-8")
        self.assertIn("Blueprint not actively producing", stress)
        self.assertIn("Factory stopped actively producing during stress", stress)


if __name__ == "__main__":
    unittest.main()
