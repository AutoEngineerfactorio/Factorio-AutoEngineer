"""Run the real helper Lua without driving the desktop or a game save."""

import unittest
from pathlib import Path
from typing import Any, cast

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("Install tests/requirements-lua.txt to run input-helper Lua tests")

MOD = Path(__file__).resolve().parents[1] / "factorio-mod/autoengineer-input_2.1.23"


def lua_globals(lua: LuaRuntime) -> Any:
    """Expose dynamically defined Lua globals only at this interop boundary."""
    return cast(Any, lua.globals())


class InputHelperTests(unittest.TestCase):
    def runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=False)
        lua_globals(lua).package.path = str(MOD / "?.lua").replace("\\", "/")
        lua.execute("""
          storage={}; handlers={}; calls={}
          defines={events={on_player_controller_changed=1,on_player_driving_changed_state=2,
            on_player_changed_surface=3,on_pre_player_died=4,on_player_left_game=5,
            on_player_respawned=6}}
          script={on_event=function(event,fn) handlers[event]=fn end}
          remote={interfaces={autoengineer_control={takeover=true}},
            add_interface=function(name,methods) remote.interfaces[name]=methods end,
            call=function(name,method,index) calls[#calls+1]=index end}
          game={get_player=function(index) if index==1 then return {} end end}
        """)
        lua.execute((MOD / "control.lua").read_text())
        return lua

    def test_linked_controls_do_not_consume_human_input(self):
        lua = LuaRuntime(unpack_returned_tuples=False)
        lua_globals(lua).package.path = str(MOD / "?.lua").replace("\\", "/")
        lua.execute("data={extend=function(self,values) prototypes=values end}")
        lua.execute((MOD / "data.lua").read_text())
        controls = set()
        for _, prototype in lua_globals(lua).prototypes.items():
            self.assertEqual(prototype.consuming, "none")
            self.assertEqual(prototype.key_sequence, "")
            controls.add(prototype.linked_game_control)
        self.assertTrue(
            {"move-up", "move-down", "move-left", "move-right", "mine", "build", "shoot-enemy"}
            <= controls
        )

    def test_all_control_and_lifecycle_handlers_revoke_and_increment(self):
        lua = self.runtime()
        count = 0
        for _, handler in lua_globals(lua).handlers.items():
            handler(lua.table_from({"player_index": 1}))
            count += 1
        self.assertGreater(count, 10)
        state = lua_globals(lua).remote.interfaces.autoengineer_input.state(1)
        self.assertEqual(state.generation, count)
        self.assertEqual(len(lua_globals(lua).calls), count)
        self.assertEqual(lua_globals(lua).remote.interfaces.autoengineer_input.state(2).generation, 0)

    def test_adapter_without_backend_keeps_human_input_available(self):
        lua = self.runtime()
        lua.execute("remote.interfaces.autoengineer_control=nil")
        lua_globals(lua).handlers["autoengineer-human-move-up"](lua.table_from({"player_index": 1}))
        self.assertEqual(lua_globals(lua).remote.interfaces.autoengineer_input.state(1).generation, 1)
