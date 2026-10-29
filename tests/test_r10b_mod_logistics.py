"""R10-B contract tests for the mod-side inventory and logistics handlers.

These tests run the **real** mod Lua in a lupa runtime against a shim that
mirrors the Factorio 2.1.23 API shapes recorded in
``memory/R10_B_API_FACTS_2123.md``. They exercise the real parser, the real
dispatcher and the real handlers, so a Lua syntax error, a wrong API name
or a wrong data shape fails here rather than in a live game.

No game process, no save, no network.

The shim deliberately covers the awkward cases the mission calls out:
missing and empty inventories, machines with several inventory types, an
unsupported inventory category, item quality, fluid inventories with a
temperature, several surfaces, several logistic networks, robot counts,
cargo and fluid wagons, and modded machines with an unusual layout.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, cast

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest(
        "Install tests/requirements-lua.txt to run the mod observation tests")

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "factorio-mod/autoengineer-input_2.1.23"
CONTROL = MOD / "control.lua"

#: The observation modules the control stage loads, in load order.
MODULES = (
    "observation", "observation_parse", "observation_telemetry",
    "observation_map", "observation_terrain", "observation_overlay",
    "observation_overlay_entities", "observation_inventory",
    "observation_logistics", "observation_capabilities", "observation_catalog",
)

#: The operations the R10-B logistics module provides.
LOGISTICS_OPERATIONS = ("machine_inventories", "logistics", "robots",
                         "transport")

#: The complete 2.1.23 ``defines.inventory`` enum, transcribed from the
#: offline archive. The shim declares exactly these members, so a handler
#: that names an identifier outside this set finds nothing and must report
#: the inventory as absent rather than as empty.
INVENTORY_ENUM = {
    "fuel": 1, "burnt_result": 2, "chest": 3, "logistic_container_trash": 4,
    "character_main": 5, "character_guns": 6, "character_ammo": 7,
    "character_armor": 8, "character_vehicle": 9, "character_trash": 10,
    "god_main": 11, "editor_main": 12, "editor_guns": 13, "editor_ammo": 14,
    "editor_armor": 15, "roboport_robot": 16, "roboport_material": 17,
    "robot_cargo": 18, "robot_repair": 19, "assembling_machine_dump": 20,
    "lab_input": 21, "lab_modules": 22, "lab_trash": 23,
    "mining_drill_modules": 24, "item_main": 25, "rocket_silo_rocket": 26,
    "rocket_silo_trash": 27, "rocket_silo_attached_cargo_unit": 28,
    "cargo_unit": 29, "car_trunk": 30, "car_ammo": 31, "car_trash": 32,
    "cargo_wagon": 33, "turret_ammo": 34, "beacon_modules": 35,
    "character_corpse": 36, "artillery_turret_ammo": 37,
    "artillery_wagon_ammo": 38, "spider_trunk": 39, "spider_ammo": 40,
    "spider_trash": 41, "hub_main": 42, "hub_trash": 43,
    "cargo_landing_pad_main": 44, "cargo_landing_pad_trash": 45,
    "proxy_main": 46, "agricultural_tower_input": 47,
    "agricultural_tower_output": 48, "agricultural_tower_modules": 49,
    "linked_container_main": 50, "crafter_input": 51, "crafter_output": 52,
    "crafter_modules": 53, "crafter_trash": 54,
    "asteroid_collector_output": 55, "asteroid_collector_arm": 56,
}

#: The 2.1.23 ``defines.logistic_member_index`` enum.
LOGISTIC_MEMBER_ENUM = {
    "logistic_container": 1, "logistic_container_trash_provider": 2,
    "vehicle_storage": 3, "character_requester": 4, "character_storage": 5,
    "character_provider": 6, "generic_on_off_behavior": 7,
    "spidertron_requester": 8, "spidertron_provider": 9, "car_requester": 10,
    "car_provider": 11, "roboport_provider": 12, "roboport_requester": 13,
    "rocket_silo_provider": 14, "rocket_silo_requester": 15,
    "rocket_silo_trash_provider": 16, "space_platform_hub_requester": 17,
    "space_platform_hub_provider": 18, "cargo_landing_pad_requester": 19,
    "cargo_landing_pad_provider": 20, "cargo_landing_pad_trash_provider": 21,
}


def lua_enum_source(mapping: dict) -> str:
    """Return a Lua table constructor for a Python mapping.

    Lua table constructors use ``key = value``, not JSON's ``"key": value``,
    so the mapping is rendered explicitly instead of being dumped as JSON.
    """
    if not mapping:
        return "{}"
    parts = ", ".join(f'["{name}"]={value}' for name, value in mapping.items())
    return "{" + parts + "}"


SHIM = """
storage={}; handlers={}; calls={}; remote_calls={}; messages={}; rcon_messages={}
__CALLS__={}; __UNIT_NUMBER__=0
commands={registered={}, add_command=function(name, help, fn)
    assert(not commands.registered[name]); commands.registered[name]=fn
  end}
defines={events={on_player_controller_changed=1,on_player_driving_changed_state=2,
  on_player_changed_surface=3,on_pre_player_died=4,on_player_left_game=5,
  on_player_respawned=6},
  controllers={character=0},
  inventory=__INVENTORY_ENUM__,
  logistic_member_index=__LOGISTIC_MEMBER_ENUM__,
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


def build_shim() -> str:
    """Return the shim source with the two enums filled in."""
    return (SHIM
            .replace("__INVENTORY_ENUM__", lua_enum_source(INVENTORY_ENUM))
            .replace("__LOGISTIC_MEMBER_ENUM__",
                     lua_enum_source(LOGISTIC_MEMBER_ENUM)))


class ModRuntime:
    """One loaded mod control stage with an injectable game world."""

    def __init__(self, runtime: Any, globals_: Any):
        self.runtime = runtime
        self.globals_ = globals_

    def observe(self, parameter: str) -> dict:
        """Run one observation and return the parsed answer document."""
        self.globals_.rcon_messages = self.runtime.table_from([])
        handler = self.globals_.commands.registered["autoengineer-observe"]
        handler(self.runtime.table_from({"parameter": parameter}))
        messages = cast(Any, self.globals_.rcon_messages)
        assert len(messages) >= 1, "the observation produced no answer"
        return json.loads(messages[1])


def load_mod(world_lua: str = "") -> ModRuntime:
    """Load the mod's control stage with the shim and an optional world."""
    runtime = LuaRuntime(unpack_returned_tuples=False)
    globals_ = cast(Any, runtime.globals())
    globals_.package.path = str(MOD / "?.lua").replace("\\", "/")
    runtime.execute(build_shim())
    if world_lua:
        runtime.execute(world_lua)
    for name in MODULES:
        source = MOD / f"{name}.lua"
        runtime.execute(
            f'package.preload["{name}"] = function() '
            f'  return dofile("{source.as_posix()}") end'
        )
    runtime.execute(CONTROL.read_text(encoding="utf-8"))
    return ModRuntime(runtime, globals_)


# ---------------------------------------------------------------------------
# the world shims
# ---------------------------------------------------------------------------

#: The shared helpers of every world. They build inventories, qualities,
#: entities, surfaces, networks, trains and a connected player.
WORLD_HELPERS = """
local function make_inventory(slots, contents)
  local inv={}
  inv.get_contents=function()
    local rows={}
    for _,entry in ipairs(contents) do rows[#rows+1]=entry end
    return rows
  end
  inv.get_bar=function() return 0 end
  setmetatable(inv,{__len=function() return slots end})
  return inv
end

local function quality(name) return {name=name} end

local function make_entity(spec)
  local entity={}
  entity.name=spec.name
  entity.type=spec.type
  entity.valid=spec.valid~=false
  entity.active=spec.active~=false
  entity.quality=quality(spec.quality or 'normal')
  entity.position={x=spec.x or 0, y=spec.y or 0}
  entity.crafting_progress=spec.progress or 0
  __UNIT_NUMBER__ = __UNIT_NUMBER__ + 1
  -- The 2.1.23 archive types ``LuaEntity.unit_number`` as ``uint64``
  -- with ``optional=True``, so an entity that is not a unit has no unit
  -- number at all.
  if not spec.no_unit_number then
    entity.unit_number=spec.unit_number or __UNIT_NUMBER__
  end
  entity.__inventories=spec.inventories or {}
  entity.__fluids=spec.fluids or {}
  entity.__fluid_temperature=spec.fluid_temperature
  entity.__recipe=spec.recipe
  entity.__train=spec.train
  -- The Factorio userdata methods are called with the dot syntax, and the
  -- game passes the entity as the receiver. A plain Lua table does not,
  -- so the shim declares the methods with the dot syntax and reads their
  -- arguments from the first parameter.
  function entity.get_inventory(index)
    for _,entry in ipairs(entity.__inventories) do
      if entry.identifier==index then return entry.inventory end
    end
    return nil
  end
  function entity.get_fuel_inventory()
    for _,entry in ipairs(entity.__inventories) do
      if entry.identifier==defines.inventory.fuel then return entry.inventory end
    end
    return nil
  end
  function entity.get_module_inventory()
    for _,entry in ipairs(entity.__inventories) do
      if entry.identifier==defines.inventory.lab_modules
        or entry.identifier==defines.inventory.mining_drill_modules
        or entry.identifier==defines.inventory.beacon_modules then
        return entry.inventory
      end
    end
    return nil
  end
  function entity.get_output_inventory() return nil end
  function entity.get_burnt_result_inventory() return nil end
  function entity.get_fluid_contents() return entity.__fluids end
  function entity.get_fluid(index)
    local name=nil
    for fluid_name in pairs(entity.__fluids) do name=fluid_name break end
    if name==nil then return nil end
    return {name=name, temperature=entity.__fluid_temperature or 0}
  end
  function entity.get_recipe()
    if entity.__recipe==nil then return nil end
    return {name=entity.__recipe}
  end
  function entity.get_train() return entity.__train end
  return entity
end

local function make_network(spec)
  local network={}
  network.network_id=spec.id
  network.custom_name=spec.name or ''
  network.valid=spec.valid~=false
  network.force=nil
  network.available_logistic_robots=spec.available_logistic or 0
  network.all_logistic_robots=spec.all_logistic or 0
  network.available_construction_robots=spec.available_construction or 0
  network.all_construction_robots=spec.all_construction or 0
  network.robot_limit=spec.limit or 0
  network.providers=spec.providers or {}
  network.requesters=spec.requesters or {}
  network.storages=spec.storages or {}
  function network:get_contents()
    local rows={}
    for _,entry in ipairs(spec.contents or {}) do rows[#rows+1]=entry end
    return rows
  end
  return network
end

local function make_surface(name, index, entities)
  local surface={}
  surface.name=name
  surface.index=index
  surface.valid=true
  -- The Factorio userdata methods are called with the dot syntax, and the
  -- game passes the surface as the receiver. A plain Lua table does not,
  -- so the shim declares the methods with the dot syntax and reads the
  -- filter from the first argument. The observation calls the methods the
  -- Factorio way, which is what the shim mirrors.
  function surface.find_entities_filtered(filter)
    assert(filter~=nil, "the filter must be the first argument")
    -- The 2.1.23 filter has no "area" for a whole-surface search, so the
    -- shim only honours the type filter and the limit.
    assert(filter.area==nil, "the whole-surface search must not name an area")
    local rows={}
    local wanted=filter.type
    for _,entity in ipairs(entities) do
      local matched=true
      if wanted~=nil then
        if type(wanted)=='table' then matched=wanted[entity.type] or false
        else matched=(wanted==entity.type) end
      end
      if matched then
        rows[#rows+1]=entity
        if filter.limit and #rows>=filter.limit then break end
      end
    end
    return rows
  end
  function surface.count_entities_filtered(filter)
    assert(filter~=nil, "the filter must be the first argument")
    assert(filter.area==nil, "the whole-surface count must not name an area")
    -- The 2.1.23 build rejects an array of types, so the shim refuses
    -- that shape too. The observation has to count one type at a time.
    if filter.type~=nil and type(filter.type)=='table' then
      error("bad argument #4 of 5 to 'count_entities_filtered' (string expected)", 2)
    end
    local count=0
    local wanted=filter.type
    for _,entity in ipairs(entities) do
      local matched=true
      if wanted~=nil then
        matched=(wanted==entity.type)
      end
      if matched then count=count+1 end
    end
    __CALLS__[#__CALLS__+1]='count '..tostring(wanted)..' n='..tostring(count)
      ..' entities='..tostring(#entities)
    return count
  end
  return surface
end

local function connect_player(surface, force)
  local character=make_entity({name='character',type='character',x=0,y=0})
  character.surface=surface
  local player={index=1, controller_type=defines.controllers.character,
    character=character, force=force}
  game.connected_players={player}
  game.get_player=function(index)
    if index==1 then return player end
    return nil
  end
  return player
end
"""


def world(entities_by_surface: dict, networks_by_surface: dict,
          *, force_name: str = "player") -> str:
    """Return a complete world shim.

    ``entities_by_surface`` maps a surface name to a list of entity
    snippets, and ``networks_by_surface`` maps a surface name to a list of
    network snippets. The snippets are joined with a comma, so each one is
    a complete expression.
    """
    lua_surfaces = []
    for index, (name, entities) in enumerate(entities_by_surface.items(), 1):
        entries = ",\n".join(entities)
        lua_surfaces.append(
            f"__SURFACES__['{name}']=make_surface('{name}', {index}, "
            f"{{\n{entries}\n}})")
    lua_networks = []
    for surface_name, networks in networks_by_surface.items():
        entries = ",\n".join(networks)
        lua_networks.append(
            f"__NETWORKS__['{surface_name}']={{\n{entries}\n}}")
    return WORLD_HELPERS + "\n".join([
        "__SURFACES__={}",
        "__NETWORKS__={}",
        *lua_surfaces,
        *lua_networks,
        "__FORCE__={name='" + force_name + "', logistic_networks=__NETWORKS__}",
        "game.surfaces={}",
        "for name,surface in pairs(__SURFACES__) do "
        "game.surfaces[#game.surfaces+1]=surface end",
        "connect_player(__SURFACES__['nauvis'], __FORCE__)",
        "game.surfaces[1].force=__FORCE__",
    ])


#: A machine with a chest inventory holding two qualities, an empty module
#: inventory and a fuel inventory.
SIMPLE_ENTITY = """
make_entity({name='assembling-machine-1', type='assembling-machine',
  x=10, y=-20, recipe='iron-gear-wheel',
  inventories={
    {identifier=defines.inventory.chest, inventory=make_inventory(4, {
      {name='iron-plate', count=100, quality=quality('normal')},
      {name='copper-plate', count=50, quality=quality('rare')}})},
    {identifier=defines.inventory.lab_modules, inventory=make_inventory(2, {})},
    {identifier=defines.inventory.fuel, inventory=make_inventory(1, {
      {name='coal', count=25, quality=quality('normal')}})},
  }})
"""

#: A modded machine with an unusual layout: it exposes its ingredient
#: inventory through an identifier that no vanilla machine uses.
MODDED_ENTITY = """
make_entity({name='py-alien-processing-unit', type='assembling-machine',
  x=-5, y=8, recipe='alien-science-pack',
  inventories={
    {identifier=defines.inventory.chest, inventory=make_inventory(2, {
      {name='alien-matter', count=7, quality=quality('epic')}})},
  }})
"""

#: A machine with no inventory at all, and one with a fluid inventory.
FLUID_ENTITIES = [
    """
make_entity({name='storage-tank-1', type='storage-tank', x=1, y=1,
  fluids={water=500}, fluid_temperature=15})
""",
    """
make_entity({name='chemical-plant-1', type='assembling-machine', x=2, y=2,
  fluids={['heavy-oil']=1200}, fluid_temperature=25,
  inventories={
    {identifier=defines.inventory.chest, inventory=make_inventory(1, {})},
  }})
""",
]

#: A cargo wagon, a fluid wagon and a locomotive.
TRANSPORT_ENTITIES = [
    """
make_entity({name='cargo-wagon-1', type='cargo-wagon', x=3, y=3,
  inventories={
    {identifier=defines.inventory.cargo_wagon, inventory=make_inventory(8, {
      {name='iron-plate', count=400, quality=quality('normal')}})},
  }})
""",
    """
make_entity({name='fluid-wagon-1', type='fluid-wagon', x=4, y=4,
  fluids={['crude-oil']=20000}, fluid_temperature=20})
""",
    """
make_entity({name='locomotive-1', type='locomotive', x=5, y=5,
  inventories={
    {identifier=defines.inventory.fuel, inventory=make_inventory(2, {
      {name='solid-fuel', count=12, quality=quality('normal')}})},
  }})
""",
]

#: Two logistic networks with different contents and robot counts.
TWO_NETWORKS = [
    """
make_network({id=1, name='main', available_logistic=120, all_logistic=200,
  available_construction=30, all_construction=60, limit=250,
  contents={
    {name='iron-plate', count=5000, quality=quality('normal')},
    {name='copper-plate', count=2500, quality=quality('rare')},
  },
  providers={{name='provider-chest'}},
  requesters={{name='requester-chest'}},
  storages={{name='storage-chest'}}})
""",
    """
make_network({id=2, name='spare', available_logistic=10, all_logistic=10,
  available_construction=0, all_construction=0, limit=10,
  contents={{name='steel-plate', count=42, quality=quality('normal')}}})
""",
]

#: The entities of the surface used by the tests.
NAUVIS_ENTITIES = [SIMPLE_ENTITY, MODDED_ENTITY, *FLUID_ENTITIES,
                    *TRANSPORT_ENTITIES]

#: An entity that is **not** a unit, so it has no unit number. The
#: 2.1.23 archive declares ``LuaEntity.unit_number`` as ``uint64`` with
#: ``optional=True``, so an entity like a decoration or a corpse has no
#: unit number at all.
ENTITY_WITHOUT_UNIT_NUMBER = """
make_entity({name='small-biter-remnants-1', type='turret', x=7, y=9,
  no_unit_number=true,
  inventories={
    {identifier=defines.inventory.turret_ammo, inventory=make_inventory(2, {})},
  }})
"""


class ModLogisticsContractTests(unittest.TestCase):
    """The new observation handlers must work against the real Lua."""

    def setUp(self):
        self.world = world(
            {"nauvis": NAUVIS_ENTITIES},
            {"nauvis": TWO_NETWORKS},
        )
        self.mod = load_mod(self.world)

    # -- the protocol ---------------------------------------------------

    def test_every_new_operation_answers_with_the_protocol_version(self):
        for operation in LOGISTICS_OPERATIONS:
            answer = self.mod.observe(operation)
            self.assertEqual(answer["protocol"], 1, operation)
            self.assertEqual(answer["status"], "ok", operation)

    def test_a_read_without_a_player_is_unavailable_not_an_error(self):
        mod = load_mod()
        for operation in LOGISTICS_OPERATIONS:
            answer = mod.observe(operation)
            self.assertEqual(answer["status"], "unavailable", operation)
            self.assertEqual(
                answer["reason"], "no_connected_player_with_character", operation)

    def test_an_unknown_argument_is_refused(self):
        answer = self.mod.observe("machine_inventories bogus=1")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "unknown_argument")

    def test_a_malformed_page_is_refused(self):
        answer = self.mod.observe("machine_inventories page=notanumber")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "invalid_page")

    def test_an_out_of_range_page_size_is_refused(self):
        answer = self.mod.observe("machine_inventories page_size=100000")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "invalid_page_size")

    def test_a_malformed_request_is_refused_even_without_a_player(self):
        """A bad request is an error, never an availability answer."""
        mod = load_mod()
        answer = mod.observe("machine_inventories page=notanumber")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "invalid_page")

    def test_an_unknown_surface_is_refused(self):
        answer = self.mod.observe("machine_inventories surface=not-a-surface")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "unknown_surface")

    def test_surface_index_and_name_select_same_observed_entities(self):
        by_index = self.mod.observe("machine_inventories surface=1")
        by_name = self.mod.observe("machine_inventories surface=nauvis")
        self.assertEqual(by_index["status"], "ok")
        self.assertEqual(by_name["status"], "ok")
        self.assertEqual(by_index.get("rows"), by_name.get("rows"))

    def test_an_entity_without_a_unit_number_reports_no_identity(self):
        """``LuaEntity.unit_number`` is optional in 2.1.23.

        The 2.1.23 archive declares it as ``uint64`` with
        ``optional=True``, so an entity that is not a unit - a decoration,
        a corpse, a cargo pod - has no unit number at all. The observation
        must then omit the identity instead of reporting a zero, and the
        sort key must still be usable.
        """
        world_lua = world(
            {"nauvis": [ENTITY_WITHOUT_UNIT_NUMBER]},
            {"nauvis": TWO_NETWORKS},
        )
        mod = load_mod(world_lua)
        answer = mod.observe("machine_inventories")
        self.assertEqual(answer["status"], "ok", answer.get("reason"))
        rows = answer.get("rows") or []
        self.assertEqual(len(rows), 1)
        self.assertNotIn("unit_number", rows[0])

    def test_the_optional_integer_never_reaches_an_integer_slot(self):
        """The identity attributes are converted with ``tonumber``.

        The archive types ``unit_number`` as ``uint64|nil``. Assigning
        that to a variable that holds the integer literal ``0`` is the
        type error "This variable is defined as type integer. Cannot
        convert its type to number|nil". The conversion keeps the value
        a plain number and leaves an absent value absent.
        """
        source = (MOD / "observation_logistics.lua").read_text(encoding="utf-8")
        self.assertNotIn('type(value) == "number" then number = value', source)
        self.assertIn("tonumber(value)", source)
        self.assertIn("tonumber(unit)", source)

    def test_numeric_locals_avoid_conflicting_optional_integer_casts(self):
        """Page defaults may need widening; a parsed surface index does not.

        The surface index comes directly from the validated parser. Its
        inferred optional integer must not be forcibly cast to number|nil.
        """
        source = (MOD / "observation_logistics.lua").read_text(encoding="utf-8")
        self.assertNotIn("---@type number|nil\n    local index =", source)
        self.assertIn("local index = observation.integer_argument(", source)
        # Page and page size have numeric defaults and take parsed numbers.
        self.assertIn("---@type number\n    local page = 1", source)
        self.assertIn("---@type number\n    local page_size = maximum",
                      source)

    def test_the_search_reaches_the_surface(self):
        """The entity search must actually reach the surface.

        The observation reports the types it counted, so a search that
        never reaches the game is visible instead of silently reporting
        zero rows.
        """
        answer = self.mod.observe("machine_inventories")
        counted = answer.get("counted_types") or []
        self.assertTrue(counted,
                        "the entity search counted no type at all")
        self.assertIn("assembling-machine", [str(name) for name in counted])

    def test_no_method_is_called_through_a_bare_pcall(self):
        """A bare ``pcall(method, receiver)`` passes the receiver twice.

        The live game rejected it with "Arguments count error for '?':
        Expected 1 argument but 2 were given", and every machine and
        transport observation answered "entity_count_unavailable". The
        call has to be made inside a closure instead.
        """
        source = (MOD / "observation_logistics.lua").read_text(encoding="utf-8")
        self.assertNotIn("pcall(surface.", source)
        self.assertNotIn("pcall(entity.", source)
        self.assertNotIn("pcall(inventory.", source)
        self.assertNotIn("pcall(network.", source)
        self.assertNotIn("pcall(train.", source)

    def test_the_operation_names_do_not_collide(self):
        """Two modules must never claim one operation name."""
        handlers = self.mod.globals_.package.loaded["observation"]
        self.assertIsNotNone(handlers)
        catalog = (MOD / "observation_catalog.lua").read_text(encoding="utf-8")
        logistics = (MOD / "observation_logistics.lua").read_text(encoding="utf-8")
        catalog_names = set(re.findall(r"HANDLERS\.(\w+)\s*=", catalog))
        logistics_names = set(re.findall(r"HANDLERS\.(\w+)\s*=", logistics))
        self.assertEqual(catalog_names & logistics_names, set())

    # -- machine inventories --------------------------------------------

    def test_a_machine_inventory_reports_the_items_and_the_quality(self):
        answer = self.mod.observe("machine_inventories")
        rows = answer["rows"]
        machine = next(row for row in rows
                       if row["name"] == "assembling-machine-1")
        chest = next(inv for inv in machine["inventories"]
                     if inv["identifier"] == "chest")
        items = {item["name"]: item for item in chest["items"]}
        self.assertEqual(items["iron-plate"]["count"], 100)
        self.assertEqual(items["iron-plate"]["quality"], "normal")
        self.assertEqual(items["copper-plate"]["count"], 50)
        self.assertEqual(items["copper-plate"]["quality"], "rare")

    def test_a_machine_inventory_reports_its_capacity(self):
        answer = self.mod.observe("machine_inventories")
        machine = next(row for row in answer["rows"]
                       if row["name"] == "assembling-machine-1")
        chest = next(inv for inv in machine["inventories"]
                     if inv["identifier"] == "chest")
        self.assertEqual(chest["capacity"], 4)

    def test_an_empty_inventory_is_empty_and_not_absent(self):
        answer = self.mod.observe("machine_inventories")
        machine = next(row for row in answer["rows"]
                       if row["name"] == "assembling-machine-1")
        modules = next(inv for inv in machine["inventories"]
                       if inv["identifier"] == "lab_modules")
        self.assertTrue(modules["empty"])
        self.assertEqual(modules["item_count"], 0)

    def test_the_fuel_inventory_is_observed(self):
        answer = self.mod.observe("machine_inventories")
        machine = next(row for row in answer["rows"]
                       if row["name"] == "assembling-machine-1")
        fuel = next(inv for inv in machine["inventories"]
                    if inv["identifier"] == "fuel")
        self.assertEqual(fuel["items"][0]["name"], "coal")
        self.assertEqual(fuel["items"][0]["count"], 25)

    def test_a_machine_reports_its_identity_and_place(self):
        answer = self.mod.observe("machine_inventories")
        machine = next(row for row in answer["rows"]
                       if row["name"] == "assembling-machine-1")
        self.assertEqual(machine["type"], "assembling-machine")
        self.assertEqual(machine["surface"], "nauvis")
        self.assertEqual(machine["quality"], "normal")
        self.assertEqual(machine["x"], 10)
        self.assertEqual(machine["y"], -20)
        self.assertEqual(machine["recipe"], "iron-gear-wheel")

    def test_a_modded_machine_with_an_unusual_layout_is_still_observed(self):
        answer = self.mod.observe("machine_inventories")
        machine = next(row for row in answer["rows"]
                       if row["name"] == "py-alien-processing-unit")
        chest = next(inv for inv in machine["inventories"]
                     if inv["identifier"] == "chest")
        self.assertEqual(chest["items"][0]["name"], "alien-matter")
        self.assertEqual(chest["items"][0]["quality"], "epic")

    def test_a_machine_without_any_inventory_reports_none(self):
        answer = self.mod.observe("machine_inventories")
        tank = next(row for row in answer["rows"]
                    if row["name"] == "storage-tank-1")
        self.assertEqual(tank["inventory_count"], 0)

    def test_a_fluid_inventory_reports_the_amount_and_the_temperature(self):
        answer = self.mod.observe("machine_inventories")
        tank = next(row for row in answer["rows"]
                    if row["name"] == "storage-tank-1")
        self.assertEqual(tank["fluids"][0]["name"], "water")
        self.assertEqual(tank["fluids"][0]["amount"], 500)
        self.assertEqual(tank["fluids"][0]["temperature"], 15)

    # -- logistic networks ----------------------------------------------

    def test_a_logistic_network_reports_its_contents(self):
        answer = self.mod.observe("logistics")
        self.assertEqual(answer["total"], 2)
        network = next(row for row in answer["rows"] if row["network_id"] == 1)
        items = {item["name"]: item for item in network["items"]}
        self.assertEqual(items["iron-plate"]["count"], 5000)
        self.assertEqual(items["copper-plate"]["quality"], "rare")

    def test_a_logistic_network_reports_its_members(self):
        answer = self.mod.observe("logistics")
        network = next(row for row in answer["rows"] if row["network_id"] == 1)
        self.assertEqual(network["providers"], ["provider-chest"])
        self.assertEqual(network["requesters"], ["requester-chest"])
        self.assertEqual(network["storages"], ["storage-chest"])

    def test_two_networks_are_never_merged(self):
        answer = self.mod.observe("logistics")
        self.assertEqual(len(answer["rows"]), 2)
        first = next(row for row in answer["rows"] if row["network_id"] == 1)
        second = next(row for row in answer["rows"] if row["network_id"] == 2)
        names = {item["name"] for item in first["items"]}
        other = {item["name"] for item in second["items"]}
        self.assertEqual(names & other, set())

    def test_a_network_reports_its_robot_availability(self):
        answer = self.mod.observe("logistics")
        network = next(row for row in answer["rows"] if row["network_id"] == 1)
        self.assertEqual(network["available_logistic_robots"], 120)
        self.assertEqual(network["all_logistic_robots"], 200)
        self.assertEqual(network["available_construction_robots"], 30)
        self.assertEqual(network["all_construction_robots"], 60)

    # -- robots ---------------------------------------------------------

    def test_the_robot_counts_are_aggregated_over_the_networks(self):
        answer = self.mod.observe("robots")
        self.assertEqual(answer["total_logistic_robots"], 210)
        self.assertEqual(answer["available_logistic_robots"], 130)
        self.assertEqual(answer["total_construction_robots"], 60)
        self.assertEqual(answer["available_construction_robots"], 30)
        self.assertEqual(answer["robot_limit"], 260)
        self.assertEqual(answer["networks"], 2)

    # -- transport ------------------------------------------------------

    def test_a_cargo_wagon_reports_its_inventory(self):
        answer = self.mod.observe("transport")
        wagon = next(row for row in answer["rows"]
                     if row["name"] == "cargo-wagon-1")
        inventory = next(inv for inv in wagon["inventories"]
                         if inv["identifier"] == "cargo_wagon")
        self.assertEqual(inventory["items"][0]["name"], "iron-plate")
        self.assertEqual(inventory["items"][0]["count"], 400)

    def test_a_fluid_wagon_reports_its_fluid(self):
        answer = self.mod.observe("transport")
        wagon = next(row for row in answer["rows"]
                     if row["name"] == "fluid-wagon-1")
        self.assertEqual(wagon["fluids"][0]["name"], "crude-oil")
        self.assertEqual(wagon["fluids"][0]["amount"], 20000)

    def test_a_locomotive_reports_its_fuel_inventory(self):
        answer = self.mod.observe("transport")
        loco = next(row for row in answer["rows"]
                    if row["name"] == "locomotive-1")
        fuel = next(inv for inv in loco["inventories"]
                    if inv["identifier"] == "fuel")
        self.assertEqual(fuel["items"][0]["name"], "solid-fuel")
        self.assertEqual(fuel["items"][0]["count"], 12)

    # -- pagination and bounds ------------------------------------------

    def test_the_page_boundary_is_deterministic(self):
        """Two reads of the same factory return the same page."""
        first = self.mod.observe("machine_inventories page=1 page_size=2")
        second = self.mod.observe("machine_inventories page=1 page_size=2")
        self.assertEqual([row["name"] for row in first["rows"]],
                         [row["name"] for row in second["rows"]])

    def test_the_pages_do_not_overlap(self):
        first = self.mod.observe("machine_inventories page=1 page_size=2")
        second = self.mod.observe("machine_inventories page=2 page_size=2")
        names = ([row["name"] for row in first["rows"]]
                 + [row["name"] for row in second["rows"]])
        self.assertEqual(len(names), len(set(names)))

    def test_a_page_beyond_the_end_is_empty_and_not_an_error(self):
        answer = self.mod.observe("machine_inventories page=500")
        self.assertEqual(answer["status"], "ok")
        self.assertEqual(answer["row_count"], 0)

    def test_the_snapshot_token_is_reported(self):
        answer = self.mod.observe("machine_inventories")
        self.assertTrue(answer["snapshot"])
        self.assertIn(":", answer["snapshot"])

    def test_the_entity_type_filter_narrows_the_read(self):
        answer = self.mod.observe(
            "machine_inventories entity_type=storage-tank")
        self.assertEqual([row["name"] for row in answer["rows"]],
                         ["storage-tank-1"])

    def test_a_malformed_entity_type_is_refused(self):
        """An empty filter value is refused by the request parser."""
        answer = self.mod.observe("machine_inventories entity_type=")
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "malformed_argument")

    def test_an_oversized_entity_type_is_refused(self):
        answer = self.mod.observe(
            "machine_inventories entity_type=" + "a" * 200)
        self.assertEqual(answer["status"], "error")
        self.assertEqual(answer["reason"], "invalid_entity_type")

    def test_the_read_is_bounded(self):
        """The handler never reports more rows than the page size."""
        answer = self.mod.observe("machine_inventories page_size=1")
        self.assertLessEqual(len(answer["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
