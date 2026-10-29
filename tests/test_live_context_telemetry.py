"""Execute bounded research/pollution telemetry against strict Lua mocks."""
import unittest
from pathlib import Path
from typing import Any, cast

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("Lua runtime unavailable")

SOURCE = Path(__file__).resolve().parents[1] / "factorio-mod/autoengineer-input_2.1.23/observation_telemetry.lua"


class ContextTelemetryTests(unittest.TestCase):
    def context(self, force, surface):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("package.loaded.observation={HANDLERS={}}")
        return cast(Any, lua.execute(SOURCE.read_text(encoding="utf-8")
            + f"\nreturn dashboard_context({force}, {surface}, {{x=1,y=2}})"))

    def test_current_research_and_local_pollution_are_observed(self):
        research, pollution = self.context("{current_research={name='mining'}, research_progress=.4}",
                                          "{get_pollution=function(p) assert(p.x==1); return 12.5 end}")
        self.assertTrue(research["active"])
        self.assertEqual(research["name"], "mining")
        self.assertAlmostEqual(research["progress"], .4)
        self.assertEqual(pollution["amount"], 12.5)
        self.assertEqual(pollution["coverage"], "character_chunk")

    def test_no_research_is_distinct_from_failed_pollution(self):
        research, pollution = self.context("{}", "{get_pollution=function() error('offline') end}")
        self.assertEqual(research["status"], "ok")
        self.assertFalse(research["active"])
        self.assertEqual(pollution["status"], "unavailable")
