"""Safety and diagnostic tests for isolated 2.1 creative fluid benchmark."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import live_py_creative_fluid as creative  # noqa: E402


class FluidCreativeTests(unittest.TestCase):
    def test_uses_factorio_21_fluid_calls_not_deleted_fluidbox(self):
        self.assertIn("e.insert_fluid", creative.FLUID_LUA)
        self.assertIn("e.extract_fluid", creative.FLUID_LUA)
        self.assertIn("rec.ingredients", creative.FLUID_LUA)
        self.assertIn("rec.products", creative.FLUID_LUA)
        self.assertNotIn("e.fluidbox", creative.FLUID_LUA)

    def test_only_disposable_surface_and_no_autonomous_actions(self):
        self.assertIn("ae-py-blueprint-stress", creative.FLUID_LUA)
        self.assertIn("s.find_entities_filtered", creative.FLUID_LUA)
        self.assertNotIn("game.surfaces[1]", creative.FLUID_LUA)
        self.assertNotIn("teleport", creative.FLUID_LUA)
        self.assertNotIn("research_all", creative.FLUID_LUA)

    def test_watch_rejects_nonloopback(self):
        rcon = Mock()
        rcon.sock.getpeername.return_value = ("192.0.2.1", 1234)
        with self.assertRaisesRegex(RuntimeError, "non-loopback"):
            creative.FeedWatch().start(rcon)

    def test_watch_rejects_wrong_private_run_credentials(self):
        rcon = Mock()
        rcon.sock.getpeername.return_value = ("127.0.0.1", 18765)
        with (patch.object(creative, "ROOT_RUNS", Path("/a")),
              patch.object(Path, "glob", return_value=[Path("/a")]),
              patch.object(creative.configparser.ConfigParser, "read", return_value=[]),
              patch.object(creative.configparser.ConfigParser, "get",
                           return_value="127.0.0.1:18764")):
            with self.assertRaisesRegex(RuntimeError, "not owned"):
                creative.FeedWatch().start(rcon)



    def test_feed_watcher_stops_before_the_owned_host_is_closed(self):
        order = []
        watcher = Mock(stalled=False, samples=[], errors=[])
        watcher.close.side_effect = lambda: order.append("feed_closed")
        blueprint = Mock()
        blueprint.is_file.return_value = True
        runs = Mock()
        runs.glob.return_value = []
        def simulate(*args, **kwargs):
            creative.live_long_stress.stop_owned(Mock())
            return 0
        with (patch.object(creative, "FeedWatch", return_value=watcher),
              patch.object(creative, "BLUEPRINT", blueprint),
              patch.object(creative, "ROOT_RUNS", runs),
              patch.object(creative.live_long_stress, "stop_owned",
                           side_effect=lambda proc: order.append("host_closed")) as stop,
              patch.object(creative.live_long_stress, "run", side_effect=simulate)):
            self.assertEqual(creative.run(1, 60, diagnose=True), 0)
            self.assertEqual(order[:2], ["feed_closed", "host_closed"])
            self.assertIs(creative.live_long_stress.stop_owned, stop)

if __name__ == "__main__":
    unittest.main()
