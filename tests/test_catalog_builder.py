"""Bounded catalog work commits only a coherent immutable epoch."""
import unittest
from pathlib import Path
from typing import Any, cast

import test_catalog_snapshot as snapshots

ROOT = Path(__file__).resolve().parents[1]


class CatalogBuilderTests(unittest.TestCase):
    def builder(self):
        lua = snapshots.CatalogSnapshotTests().runtime()
        factory = cast(Any, lua.execute((ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_catalog_builder.lua").read_text(encoding="utf-8")))
        builder = factory(lua.eval("package.loaded.observation"), lua.eval("function() return test_game.tick end"))
        return lua, builder

    def test_capture_is_pending_then_commits_same_fingerprint_and_tick(self):
        lua, builder = self.builder()
        full, _ = cast(Any, lua.eval("package.loaded.observation.capabilities(1,100000,true)"))
        caps, status = builder.get(1, 32)
        self.assertIsNone(caps)
        self.assertEqual(status["status"], "catalog_building")
        for _ in range(2):
            lua.execute("test_game.tick=test_game.tick+1")
            builder.step()
        caps, status, player, _ = builder.get(1, 32)
        self.assertEqual(caps["source_fingerprint"], full["source_fingerprint"])
        self.assertEqual(caps["tick"], 1002)
        self.assertEqual(player["tick"], 1002)
        self.assertTrue(status["coverage_complete"])
        next_caps, _, _, _ = builder.get(2, 32)
        self.assertEqual(next_caps["tick"], caps["tick"])
        self.assertEqual(len(caps["recipes"])+len(caps["excluded"])
                         +len(next_caps["recipes"])+len(next_caps["excluded"]), 40)

    def test_changed_force_inputs_never_commit_a_mixed_catalog(self):
        lua, builder = self.builder()
        builder.get(1, 32)
        builder.step()
        lua.execute("for _,recipe in pairs(test_player.force.recipes) do recipe.enabled=false end")
        builder.step()
        builder.step()
        caps, status = builder.get(1, 32)
        self.assertIsNone(caps)
        self.assertEqual(status["status"], "snapshot_changed")


    def test_force_rename_invalidates_the_capture(self):
        lua, builder = self.builder()
        builder.get(1, 32)
        builder.step()
        lua.execute("test_player.force.name='renamed'")
        builder.step()
        caps, status = builder.get(1, 32)
        self.assertIsNone(caps)
        self.assertEqual(status["status"], "snapshot_changed")

    def test_real_capability_module_registers_and_uses_the_tick_callback(self):
        lua = snapshots.LuaRuntime(unpack_returned_tuples=True)
        factory = lua.execute((ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_catalog_builder.lua").read_text(encoding="utf-8"))
        cast(Any, lua.globals()).builder_factory = factory
        setup = "RECIPE_COUNT=40;BAD_INDEX_1=10;BAD_INDEX_2=35;" + snapshots.MOCK_FORCE
        setup += """
        test_game=game
        script.on_nth_tick=function(n,handler) assert(n==1);test_tick_handler=handler end
        package.preload.observation_catalog_builder=function() return builder_factory end
        package.loaded.observation={observed_player=function() return p,c end,
          HANDLERS={status=function() return {tick=game.tick,status='ok'} end,
            inventory=function() return {tick=game.tick,status='ok'} end}}
        """
        setup += (ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_capabilities.lua").read_text(encoding="utf-8")
        lua.execute(setup)
        caps, status = cast(Any, lua.eval("package.loaded.observation.catalog_snapshot(1,32)"))
        self.assertIsNone(caps)
        self.assertEqual(status["status"], "catalog_building")
        lua.execute("for i=1,2 do test_game.tick=test_game.tick+1;test_tick_handler() end")
        caps, status, _, _ = cast(Any, lua.eval("package.loaded.observation.catalog_snapshot(1,32)"))
        self.assertEqual(caps["tick"], 1002)
        self.assertTrue(status["coverage_complete"])
