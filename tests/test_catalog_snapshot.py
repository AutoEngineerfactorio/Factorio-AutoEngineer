"""Immutable same-tick recipe paging with exclusions and expiry."""
import unittest
from pathlib import Path
from typing import Any, cast

from test_r06_recipe_accounting import MOCK_FORCE

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("lupa unavailable")

ROOT = Path(__file__).resolve().parents[1]


class CatalogSnapshotTests(unittest.TestCase):
    def runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        code = "RECIPE_COUNT=40;BAD_INDEX_1=10;BAD_INDEX_2=35;\n" + MOCK_FORCE
        code += """
        test_game=game;test_player=p;test_prototypes=prototypes
        package.loaded.observation={observed_player=function() return p,c end,
          HANDLERS={status=function() return {tick=game.tick,status='ok'} end,
            inventory=function() return {tick=game.tick,status='ok'} end}}
        """
        code += (ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_capabilities.lua").read_text(encoding="utf-8")
        lua.execute(code)
        return lua

    def test_pages_preserve_one_epoch_and_account_for_exclusions(self):
        lua = self.runtime()
        first, status, player, _ = cast(Any, lua.eval("package.loaded.observation.catalog_snapshot(1,32)"))
        self.assertFalse(first["truncated"])
        self.assertEqual(len(first["recipes"])+len(first["excluded"]),32)
        self.assertEqual(player["tick"],1000)
        cast(Any,lua.globals()).test_game.tick=1200
        second, next_status, _, _ = cast(Any,lua.eval("package.loaded.observation.catalog_snapshot(2,32)"))
        self.assertEqual(second["tick"],1000)
        self.assertEqual(next_status["observation_tick"],1200)
        self.assertEqual(status["total_pages"],2)
        self.assertEqual(first["source_fingerprint"],second["source_fingerprint"])
        self.assertEqual(len(second["recipes"])+len(second["excluded"]),8)

    def test_missing_or_expired_snapshot_requires_refresh(self):
        lua=self.runtime()
        caps,status=cast(Any,lua.eval("package.loaded.observation.catalog_snapshot(2,32)"))
        self.assertIsNone(caps)
        self.assertEqual(status["status"],"snapshot_expired")
        lua.eval("package.loaded.observation.catalog_snapshot(1,32)")
        cast(Any,lua.globals()).test_game.tick=20000
        caps,status=cast(Any,lua.eval("package.loaded.observation.catalog_snapshot(2,32)"))
        self.assertIsNone(caps)
        self.assertEqual(status["status"],"snapshot_expired")


    def test_observed_electric_power_and_drain_use_watts(self):
        lua = self.runtime()
        lua.execute("""test_prototypes.entity.machine={type='assembling-machine',
            crafting_categories={crafting=true}, energy_usage=2500,
            electric_energy_source_prototype={drain=83.33333333333333},
            get_crafting_speed=function() return 0.75 end}""")
        caps, _, _, _ = cast(Any, lua.eval("package.loaded.observation.catalog_snapshot(1,32)"))
        row = caps["machines"][1]
        self.assertEqual(row["energy_usage"], 150000)
        self.assertAlmostEqual(row["energy_drain"], 5000)


    def test_large_researched_modpack_keeps_complete_technology_coverage(self):
        lua = self.runtime()
        lua.execute("""for i=1,2000 do
            test_player.force.technologies['technology-'..i]={researched=true,enabled=true,
                level=1,prototype={effects={}}}
            end""")
        caps, status, _, _ = cast(Any, lua.eval("package.loaded.observation.catalog_snapshot(1,32)"))
        self.assertEqual(len(caps["research"]), 2000)
        self.assertFalse(caps["truncated"])
        self.assertTrue(status["coverage_complete"])


    def test_batched_capabilities_preserve_full_fingerprint_and_coverage(self):
        lua = self.runtime()
        full, _ = cast(Any, lua.eval("package.loaded.observation.capabilities(1,100000,true)"))
        lua.execute("batch_context={}")
        total = 0
        last = None
        for page in range(1, 4):
            last, _ = cast(Any, lua.eval(
                f"package.loaded.observation.capabilities({page},16,true,batch_context)"))
            total += len(last["recipes"]) + len(last["excluded"])
        self.assertEqual(total, 40)
        assert last is not None
        self.assertEqual(last["source_fingerprint"], full["source_fingerprint"])
