"""Safety and identity checks for the retrieved Pyanodons production blueprint."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from live_blueprint_stress import inspect_blueprint  # noqa: E402

BLUEPRINT = ROOT / ".local/blueprint-stress/py-oxygen-nitrogen-source.txt"


class BlueprintStressTests(unittest.TestCase):
    def test_blueprint_matches_reviewed_1225_entity_pyanodons_factory(self):
        result = inspect_blueprint(BLUEPRINT)
        self.assertEqual(result["entities_per_copy"], 1225)
        self.assertEqual(result["names"]["distilator"], 72)
        self.assertEqual(result["names"]["vacuum-pump-mk01"], 6)
        self.assertEqual(result["recipes"]["purest-nitrogen-gas"], 72)

    def test_creative_changes_restricted_to_disposable_blueprint_surface(self):
        source = (ROOT / "tests/live_blueprint_stress.py").read_text(encoding="utf-8")
        self.assertIn("AE_BP_GATE_READY", source)
        self.assertIn("ae-py-blueprint-stress", source)
        self.assertIn("import_stack", source)
        self.assertIn("build_blueprint", source)
        self.assertIn("silent_revive", source)
        self.assertIn("skip_fog_of_war=false", source)
        self.assertIn("AE_BP_BAD_IMPORT", source)
        self.assertIn("revival_coverage", source)
        self.assertIn("placement_complete", source)
        self.assertNotIn("/silent-command", source)

    def test_long_stress_requires_pyanodons_for_this_blueprint(self):
        from live_long_stress import run

        with self.assertRaises(ValueError):
            run("vanilla", 300, blueprint_file=BLUEPRINT, replicas=2)
        with self.assertRaises(ValueError):
            run("py", 300, blueprint_file=BLUEPRINT, replicas=0)


if __name__ == "__main__":
    unittest.main()
