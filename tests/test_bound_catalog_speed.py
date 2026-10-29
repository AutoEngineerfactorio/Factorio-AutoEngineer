"""Bound runtime methods must receive no implicit receiver."""
import unittest
from pathlib import Path
from typing import Any, cast

from test_r06_machine_prototype import MOCK_RUNTIME

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("lupa unavailable")

ROOT = Path(__file__).resolve().parents[1]


class BoundCatalogSpeedTests(unittest.TestCase):
    def test_active_catalog_uses_bound_method(self):
        source = (ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_capabilities.lua").read_text(encoding="utf-8")
        start = source.index("local machines, machines_truncated = {}, false")
        end = source.index("catalog_status.fingerprint_nodes", start)
        runtime = MOCK_RUNTIME.replace("function(self, quality)",
                                       "function(...) assert(select('#',...) == 0)")
        rows = cast(Any, LuaRuntime(unpack_returned_tuples=True).execute(runtime + source[start:end] + " return machines"))
        machine = next(row for _, row in rows.items() if row["name"] == "assembling-machine-1")
        self.assertEqual(machine["crafting_speed"], 0.75)
        self.assertEqual(machine["module_slots"], 2)
