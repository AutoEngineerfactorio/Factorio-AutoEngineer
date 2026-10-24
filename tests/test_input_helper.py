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
          storage={}; handlers={}; calls={}; remote_calls={}; messages={}
          commands={registered={}, add_command=function(name, help, fn)
              assert(not commands.registered[name]); commands.registered[name]=fn
          end}
          defines={events={on_player_controller_changed=1,on_player_driving_changed_state=2,
            on_player_changed_surface=3,on_pre_player_died=4,on_player_left_game=5,
            on_player_respawned=6}}
          script={on_event=function(event,fn) handlers[event]=fn end}
          remote={interfaces={autoengineer_control={takeover=true}},
            add_interface=function(name,methods) remote.interfaces[name]=methods end,
            call=function(name,method,index)
              calls[#calls+1]=index
              remote_calls[#remote_calls+1]={name,method,index}
            end}
          game={get_player=function(index) if index==1 then
            return {print=function(msg) messages[#messages+1]=msg end} end end}
        """)
        lua.execute((MOD / "control.lua").read_text())
        return lua

    def test_takeover_remote_call_preserves_dynamic_interface_contract(self):
        lua = self.runtime()
        lua_globals(lua).handlers["autoengineer-human-move-up"](
            lua.table_from({"player_index": 1}))
        remote_call = lua_globals(lua).remote_calls[1]
        self.assertEqual((remote_call[1], remote_call[2], remote_call[3]),
                         ("autoengineer_control", "takeover", 1))

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

    def test_registered_status_command_is_read_only_and_single_invocation(self):
        lua = self.runtime()
        globals_ = lua_globals(lua)
        status = globals_.commands.registered["autoengineer-status"]
        self.assertIsNotNone(status)
        before = globals_.remote.interfaces.autoengineer_input.state(1).generation
        status(lua.table_from({"player_index": 1}))
        self.assertEqual(globals_.remote.interfaces.autoengineer_input.state(1).generation, before)
        self.assertEqual(len(globals_.calls), 0)
        self.assertEqual(len(globals_.messages), 1)
        self.assertIn("input guard active", globals_.messages[1])
        self.assertIn("See the dashboard for AI connection/status", globals_.messages[1])

    def test_registered_takeover_requests_one_human_revocation(self):
        lua = self.runtime()
        globals_ = lua_globals(lua)
        callback = globals_.commands.registered["autoengineer-takeover"]
        self.assertIsNotNone(callback)
        callback(lua.table_from({"player_index": 1}))
        self.assertEqual(globals_.remote.interfaces.autoengineer_input.state(1).generation, 1)
        self.assertEqual(list(globals_.calls.values()), [1])
        self.assertEqual(len(globals_.messages), 1)
        self.assertIn("human takeover requested", globals_.messages[1])

    def test_takeover_generation_increments_once_per_explicit_execution(self):
        lua = self.runtime()
        globals_ = lua_globals(lua)
        callback = globals_.commands.registered["autoengineer-takeover"]
        callback(lua.table_from({"player_index": 1}))
        self.assertEqual(globals_.remote.interfaces.autoengineer_input.state(1).generation, 1)
        callback(lua.table_from({"player_index": 1}))
        self.assertEqual(globals_.remote.interfaces.autoengineer_input.state(1).generation, 2)
        self.assertEqual(list(globals_.calls.values()), [1, 1])

    def test_commands_are_registered_once_without_lua_console_path(self):
        lua = self.runtime()
        globals_ = lua_globals(lua)
        self.assertEqual(
            set(globals_.commands.registered),
            {"autoengineer-status", "autoengineer-takeover"},
        )
        self.assertNotIn("lua", globals_.commands.registered)
        self.assertNotIn("c", globals_.commands.registered)
        source = (MOD / "control.lua").read_text()
        self.assertIn('commands.add_command("autoengineer-status"', source)
        self.assertIn('commands.add_command("autoengineer-takeover"', source)
        self.assertNotIn('"/c', source)

    def test_commands_work_when_ai_backend_is_unavailable(self):
        lua = self.runtime()
        lua.execute("remote.interfaces.autoengineer_control=nil")
        globals_ = lua_globals(lua)
        globals_.commands.registered["autoengineer-status"](lua.table_from({"player_index": 1}))
        self.assertIn("input guard active", globals_.messages[1])
        globals_.commands.registered["autoengineer-takeover"](lua.table_from({"player_index": 1}))
        self.assertEqual(globals_.remote.interfaces.autoengineer_input.state(1).generation, 1)
        self.assertEqual(len(globals_.calls), 0)

    def test_console_commands_do_not_act_without_an_actual_player(self):
        lua = self.runtime()
        globals_ = lua_globals(lua)
        for name in ("autoengineer-status", "autoengineer-takeover"):
            for player_index in (None, 2):
                args = {} if player_index is None else {"player_index": player_index}
                globals_.commands.registered[name](lua.table_from(args))
        self.assertEqual(len(globals_.calls), 0)
        self.assertEqual(len(globals_.messages), 0)
        self.assertEqual(globals_.remote.interfaces.autoengineer_input.state(1).generation, 0)

    def test_adapter_without_backend_keeps_human_input_available(self):
        lua = self.runtime()
        lua.execute("remote.interfaces.autoengineer_control=nil")
        lua_globals(lua).handlers["autoengineer-human-move-up"](lua.table_from({"player_index": 1}))
        self.assertEqual(lua_globals(lua).remote.interfaces.autoengineer_input.state(1).generation, 1)
