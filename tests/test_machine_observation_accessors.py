"""Execute the machine observer with bound Factorio 2.1.23 API methods."""
import unittest
from pathlib import Path
from typing import Any, cast

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("lupa unavailable")

ROOT = Path(__file__).resolve().parents[1]


class MachineAccessorTests(unittest.TestCase):
    def test_bound_speed_method_and_fluidbox_metadata(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
        local obs = {HANDLERS={}, observed_player=function() return {} end,
          ok=function(x) return x end, error_status=function(e) error(e) end}
        package.loaded.observation=obs
        package.loaded.observation_capabilities={}
        prototypes={entity={machine=setmetatable({type='assembling-machine',
          crafting_categories={crafting=true}, module_inventory_size=2,
          energy_usage=2500, fluidbox_prototypes={{volume=100}},
          allowed_module_categories={speed=true},
          get_crafting_speed=function(...)
            assert(select('#',...)==0,'bound method received a receiver')
            return 0.75
          end}, {__index=function(_,key) error('undeclared member '..key) end})}}
        """)
        lua.execute((ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_catalog.lua")
                    .read_text(encoding="utf-8"))
        row = cast(Any, lua.eval("package.loaded.observation.HANDLERS.machines({}).rows[1]"))
        self.assertEqual(row["energy_usage"], 150000)
        self.assertEqual(row["speed"], 0.75)
        self.assertEqual(row["module_slots"], 2)
        self.assertEqual(row["fluid_boxes"][1]["volume"], 100)


if __name__ == "__main__":
    unittest.main()
