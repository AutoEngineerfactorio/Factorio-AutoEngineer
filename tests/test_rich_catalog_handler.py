"""Execute registered rich-catalog routing and paging denial paths."""
import unittest
from pathlib import Path
from typing import Any, cast

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("lupa unavailable")

ROOT = Path(__file__).resolve().parents[1]


class RichCatalogHandlerTests(unittest.TestCase):
    def test_preserves_full_envelope_and_validates_bounds(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
        local obs={HANDLERS={},ok=function(x) return x end,
          unavailable=function(e) return {status='unavailable',reason=e} end,
          error_status=function(e) return {status='error',reason=e} end,
          integer_argument=function(value,lo,hi)
            local number=tonumber(value)
            if number and number>=lo and number<=hi then return number end
          end}
        obs.catalog_snapshot=function(page,size)
          assert(page==1 and (size==16 or size==128))
          return {schema=1,tick=42,machines={{crafting_speed=.75}},source_fingerprint='fp'},
            {page=page,page_size=size,total_count=1,total_pages=1}
        end
        package.loaded.observation=obs
        package.loaded.observation_capabilities={}
        """)
        lua.execute((ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_catalog.lua").read_text(encoding="utf-8"))
        result = cast(Any, lua.eval("package.loaded.observation.HANDLERS.capabilities({page='1',page_size='16'})"))
        self.assertEqual(result["capabilities"]["source_fingerprint"], "fp")
        self.assertEqual(result["capabilities"]["machines"][1]["crafting_speed"], .75)
        bad = cast(Any, lua.eval("package.loaded.observation.HANDLERS.capabilities({page='0',page_size='16'})"))
        self.assertEqual(bad["status"], "error")

        large = cast(Any, lua.eval("package.loaded.observation.HANDLERS.capabilities({page='1',page_size='128'})"))
        self.assertEqual(large["catalog_status"]["page_size"],128)
        refused = cast(Any, lua.eval("package.loaded.observation.HANDLERS.capabilities({page='1',page_size='129'})"))
        self.assertEqual(refused["status"],"error")
