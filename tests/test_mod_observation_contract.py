"""Contract tests for the AutoEngineer read-only mod observation API.

The mod is the observation transport that replaces raw Lua console commands.
These tests run the mod's own Lua in a lupa runtime with a minimal Factorio
shim, so they exercise the real parser and the real dispatcher.

No game process, no save, no network.
"""
import json
import re
import unittest
from pathlib import Path
from typing import Any, cast

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("Install tests/requirements-lua.txt to run the mod observation tests")

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "factorio-mod/autoengineer-input_2.1.23"
CONTROL = MOD / "control.lua"

#: The observation modules the control stage loads, in load order.
MODULES = ("observation", "observation_parse", "observation_telemetry",
           "observation_map", "observation_terrain", "observation_overlay",
           "observation_overlay_entities", "observation_inventory",
           "observation_capabilities", "observation_catalog")


def present_modules():
    """Return the observation modules that exist in the mod source."""
    return [name for name in MODULES if (MOD / f"{name}.lua").is_file()]


#: The operations each module provides. An operation whose module is absent
#: is not registered yet, so the dispatcher answers "unknown_operation".
PROVIDED_OPERATIONS = {
    "observation": ("status",),
    "observation_telemetry": ("telemetry",),
    "observation_map": ("map",),
    "observation_terrain": ("terrain",),
    "observation_overlay": ("overlay",),
    "observation_inventory": ("inventory",),
    "observation_catalog": ("recipes", "research", "machines"),
}


def implemented_operations():
    """Return the operations the loaded modules actually provide."""
    operations = []
    for name in present_modules():
        operations.extend(PROVIDED_OPERATIONS.get(name, ()))
    return operations

SHIM = """
storage={}; handlers={}; calls={}; remote_calls={}; messages={}; rcon_messages={}
commands={registered={}, add_command=function(name, help, fn)
    assert(not commands.registered[name]); commands.registered[name]=fn
  end}
defines={events={on_player_controller_changed=1,on_player_driving_changed_state=2,
  on_player_changed_surface=3,on_pre_player_died=4,on_player_left_game=5,
  on_player_respawned=6},
  controllers={character=0},
  inventory={character_main=0},
  flow_precision_index={one_minute=1,five_seconds=2}}
script={on_event=function(event,fn) handlers[event]=fn end}
remote={interfaces={autoengineer_control={takeover=true}},
  add_interface=function(name,methods) remote.interfaces[name]=methods end,
  call=function(name,method,index)
    calls[#calls+1]=index
    remote_calls[#remote_calls+1]={name,method,index}
  end}
helpers={table_to_json=function(t)
    local function is_array(value)
      if type(value)~='table' then return false end
      local count=0
      for key in pairs(value) do
        if type(key)~='number' then return false end
        count=count+1
      end
      return count>0
    end
    local function encode(value)
      local kind=type(value)
      if kind=='nil' then return 'null' end
      if kind=='boolean' then return tostring(value) end
      if kind=='number' then return tostring(value) end
      if kind=='string' then return string.format('%q', value) end
      if kind=='table' then
        if is_array(value) then
          local parts={}
          for _,item in ipairs(value) do parts[#parts+1]=encode(item) end
          return '['..table.concat(parts,',')..']'
        end
        local parts={}
        for key,item in pairs(value) do
          parts[#parts+1]=string.format('%q',tostring(key))..':'..encode(item)
        end
        return '{'..table.concat(parts,',')..'}'
      end
      return 'null'
    end
    return encode(t)
  end}
prototypes={entity={}, fluid={}}
game={tick=1234, connected_players={},
  get_player=function(index) return nil end}
rcon={print=function(msg) rcon_messages[#rcon_messages+1]=msg end}
"""


class ModObservationContractTests(unittest.TestCase):
    """The observation API must be read-only, validated and versioned."""

    def runtime(self):
        """Load the mod's control stage with a minimal Factorio shim."""
        lua = LuaRuntime(unpack_returned_tuples=False)
        globals_ = cast(Any, lua.globals())
        globals_.package.path = str(MOD / "?.lua").replace("\\", "/")
        lua.execute(SHIM)
        for name in present_modules():
            source = MOD / f"{name}.lua"
            lua.execute(
                f'package.preload["{name}"] = function() '
                f'  return dofile("{source.as_posix()}") end'
            )
        lua.execute(CONTROL.read_text(encoding="utf-8"))
        return lua, globals_

    def observe(self, lua, globals_, parameter):
        """Run one observation and return the parsed answer document."""
        globals_.rcon_messages = lua.table_from([])
        handler = globals_.commands.registered["autoengineer-observe"]
        handler(lua.table_from({"parameter": parameter}))
        messages = cast(Any, globals_.rcon_messages)
        self.assertGreaterEqual(len(messages), 1, "the observation produced no answer")
        return json.loads(messages[1])

    def test_the_mod_registers_the_observe_command(self):
        _lua, globals_ = self.runtime()
        registered = sorted(globals_.commands.registered.keys())
        self.assertIn("autoengineer-observe", registered)
        # The existing human-facing commands must survive.
        self.assertIn("autoengineer-status", registered)
        self.assertIn("autoengineer-takeover", registered)

    def test_an_unknown_operation_is_refused(self):
        lua, globals_ = self.runtime()
        answer = self.observe(lua, globals_, "definitely_not_an_operation")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "unknown_operation")

    def test_an_unknown_argument_is_refused(self):
        lua, globals_ = self.runtime()
        answer = self.observe(lua, globals_, "telemetry bogus=1")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "unknown_argument")

    def test_every_answer_carries_the_protocol_version(self):
        lua, globals_ = self.runtime()
        for operation in ("status", "telemetry", "map", "recipes", "research", "machines"):
            answer = self.observe(lua, globals_, operation)
            self.assertEqual(answer["protocol"], 1, operation)
            self.assertIn(answer["status"], ("ok", "unavailable", "error"), operation)

    def test_a_read_without_a_player_is_unavailable_not_an_error(self):
        lua, globals_ = self.runtime()
        for operation in implemented_operations():
            answer = self.observe(lua, globals_, operation)
            self.assertEqual(answer["status"], "unavailable", operation)
            self.assertEqual(
                answer["reason"], "no_connected_player_with_character", operation)

    def test_an_empty_parameter_is_refused(self):
        lua, globals_ = self.runtime()
        answer = self.observe(lua, globals_, "")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "missing_operation")

    def test_a_malformed_argument_is_refused(self):
        lua, globals_ = self.runtime()
        answer = self.observe(lua, globals_, "recipes page")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "malformed_argument")

    def test_a_duplicate_argument_is_refused(self):
        lua, globals_ = self.runtime()
        answer = self.observe(lua, globals_, "recipes page=1 page=2")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "duplicate_argument")

    def test_the_observation_api_contains_no_gameplay_action(self):
        """The mod must not gain a way to craft, place, move or research."""
        forbidden = (
            "create_entity", "build_from_cursor", "insert_fluid", "add_research",
            "script_trigger_research", "research_all_technologies", "set_recipe",
            "mine_entity", "destroy", "player.teleport", "set_controller",
        )
        for name in present_modules():
            source = (MOD / f"{name}.lua").read_text(encoding="utf-8")
            for action in forbidden:
                self.assertNotIn(action, source, f"{name} must not call {action}")

    def test_the_observation_api_never_evaluates_client_lua(self):
        """No dynamic Lua evaluation may reach the game from a parameter."""
        for name in present_modules():
            source = (MOD / f"{name}.lua").read_text(encoding="utf-8")
            for dangerous in ("loadstring", "load(", "dofile", "assert("):
                self.assertNotIn(dangerous, source, f"{name} must not use {dangerous}")
            # The modules may require each other, but only by a fixed
            # mod-local name that this mod owns.
            for match in source.split('require("')[1:]:
                name_only = match.split('"')[0]
                self.assertTrue(
                    is_mod_local_require(name_only),
                    f"{name} requires an unexpected module {name_only!r}",
                )


def is_mod_local_require(name: str) -> bool:
    """Whether a require path names a file this mod owns.

    Factorio resolves ``require`` **relative to the mod root**, with the
    path segments separated by dots. The ``__modname__`` prefix names
    *another* mod, so a mod must never use it for its own files. The live
    2.1.23 server rejected ``__modname__/observation`` with "Path
    __modname__/observation.lua does not match any enabled mod", and the
    installed mod ``PerfectlyGenericObject`` shows the working form for a
    mod's own file: ``require("prototypes.item.perfectly-generic-object")``.

    The rule stays strict: the path must be a plain literal that names a
    file of this mod. A cross-mod prefix, an absolute path or an
    interpolated value is refused, so no client-supplied text can ever
    reach the game as a require path.
    """
    if not name or "/" in name or "\\" in name:
        return False
    if name.startswith("__"):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        return False
    # The path must resolve to a file of this mod.
    relative = name.replace(".", "/") + ".lua"
    return (MOD / relative).is_file()


class ElectricNetworkApiContractTests(unittest.TestCase):
    def test_electric_subnetwork_id_and_parent_flow_are_separate(self):
        """2.1.23 uses subnetwork.id, never subnetwork.network_id."""
        source = (MOD / "observation_telemetry.lua").read_text(encoding="utf-8")
        self.assertIn("local id = network.id", source)
        self.assertIn("local parent = network.parent_network or network", source)
        self.assertIn("local row = electric_row(parent, game.tick, id)", source)
        self.assertIn("network_id = subnetwork_id", source)
        self.assertNotIn("network.network_id", source)


class ModLocalRequireTests(unittest.TestCase):
    """The require-path rule must stay strict.

    Changing the accepted convention must not have weakened the boundary:
    a cross-mod path, an absolute path, an interpolated value or a module
    this mod does not own is still refused.
    """

    def test_the_mods_own_modules_are_accepted(self):
        for name in ("observation", "observation_parse", "observation_telemetry"):
            self.assertTrue(is_mod_local_require(name), name)

    def test_a_cross_mod_path_is_refused(self):
        """The __modname__ prefix names another mod and is refused."""
        self.assertFalse(is_mod_local_require("__modname__/observation"))
        self.assertFalse(is_mod_local_require("__modname__.observation"))
        self.assertFalse(is_mod_local_require("__base__/core"))

    def test_an_absolute_path_is_refused(self):
        self.assertFalse(is_mod_local_require("/etc/passwd"))
        self.assertFalse(is_mod_local_require("C:\\windows\\system32"))

    def test_a_dynamic_require_is_refused(self):
        """An interpolated value can never become a require path."""
        self.assertFalse(is_mod_local_require("observation.."))
        self.assertFalse(is_mod_local_require("observation;os.execute('x')"))
        self.assertFalse(is_mod_local_require("observation?x=1"))

    def test_an_unknown_module_is_refused(self):
        """A file this mod does not own is refused."""
        self.assertFalse(is_mod_local_require("not_a_module_of_this_mod"))

    def test_the_check_still_refuses_the_live_server_failure_form(self):
        """The form the live 2.1.23 server rejected stays refused."""
        self.assertFalse(is_mod_local_require("__modname__/observation.lua"))



class StatusMetadataTests(unittest.TestCase):
    def test_status_reports_observed_version_without_catalog_scan(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
            package.loaded.observation_parse={}
            script={active_mods={base='2.1.23'}};storage={}
            remote={interfaces={}};defines={controllers={character=0}}
            game={tick=5,connected_players={{name='Engineer',controller_type=0,
                force={name='player'},character={walking_state={walking=false},
                surface={name='nauvis'},position={x=1,y=2}}}}}
        """)
        observation = cast(Any, lua.execute((MOD / "observation.lua").read_text(encoding="utf-8")))
        status = observation.HANDLERS.status()
        self.assertEqual(status["game_version"], "2.1.23")
        self.assertEqual(status["player_name"], "Engineer")
        self.assertEqual(status["tick"], 5)

if __name__ == "__main__":
    unittest.main()
