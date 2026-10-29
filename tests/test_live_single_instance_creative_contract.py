"""Safety contract of the explicitly authorized creative-item live harness."""
import unittest
from pathlib import Path

HARNESS = Path(__file__).with_name("live_single_instance_creative.py")


class SingleInstanceCreativeHarnessContracts(unittest.TestCase):
    def test_only_one_graphical_game_instance_is_launched(self):
        content = HARNESS.read_text(encoding="utf-8")
        self.assertIn('"--host", str(save)', content)
        self.assertNotIn('"--start-server"', content)
        self.assertIn("factorio.exe", content)
        self.assertIn('proc.terminate()', content)

    def test_original_save_is_copied_and_compared(self):
        content = HARNESS.read_text(encoding="utf-8")
        self.assertIn("shutil.copy2(SOURCE_SAVE, save)", content)
        self.assertIn("digest(SOURCE_SAVE) == before", content)
        self.assertIn("shutil.copytree(MODS, private_mods)", content)

    def test_creative_writes_only_after_marker_probe(self):
        content = HARNESS.read_text(encoding="utf-8")
        self.assertIn("AE_CREATIVE_GATE_OK", content)
        self.assertIn('connection.command("/c " + CREATIVE)', content)
        self.assertNotIn("ef.set_recipe", content)
        self.assertIn("ef.insert{name='iron-ore',count=80}", content)

    def test_observation_uses_the_registered_mod_command(self):
        content = HARNESS.read_text(encoding="utf-8")
        self.assertIn('"/autoengineer-observe " + kind', content)
        self.assertIn('UiFrame(', content)
        self.assertIn('qt-live-electrical.png', content)


if __name__ == "__main__":
    unittest.main()
