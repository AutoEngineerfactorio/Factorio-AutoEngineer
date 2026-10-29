"""Contracts and pure math for the long, isolated single-host stress harness."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from live_long_stress import tail_stats  # noqa: E402


class StressHarnessTests(unittest.TestCase):
    def test_ups_statistics_retain_degraded_intervals(self):
        values = [60, 60, 59.5, 57.2, 50, 60]
        data = tail_stats(values)
        self.assertEqual(data["count"], 6)
        self.assertEqual(data["minimum"], 50)
        self.assertEqual(data["below_58"], 2)
        self.assertEqual(data["below_59"], 2)

    def test_empty_observations_are_unknown(self):
        self.assertEqual(tail_stats([]), {"count": 0})

    def test_harness_requires_separate_mod_and_save_profiles(self):
        source = (ROOT / "tests/live_long_stress.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('profile_name == "vanilla"', source)
        self.assertIn('else MODDED_SAVE', source)
        self.assertIn('"space-age" not in enabled', source)
        self.assertIn('"pyalienlife" not in enabled', source)
        self.assertIn('shutil.copy2(source_save, copied)', source)
        self.assertIn('digest(source_save) == source_sha', source)

    def test_commands_are_registered_observations_and_model_only(self):
        source = (ROOT / "tests/live_long_stress.py").read_text(encoding="utf-8")
        self.assertIn('"/autoengineer-observe status"', source)
        self.assertIn('with guarded_urlopen(request, timeout=125)', source)
        self.assertNotIn('"/silent-command', source)
        self.assertNotIn('"/c ', source)
        self.assertNotIn('"--start-server"', source)
        self.assertIn('"--host", str(copied)', source)
        self.assertIn('stop_owned(llm)', source)
        self.assertIn('stop_owned(host)', source)


if __name__ == "__main__":
    unittest.main()
