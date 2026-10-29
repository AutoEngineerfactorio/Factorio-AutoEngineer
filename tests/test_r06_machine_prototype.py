"""Regression tests for the Factorio 2.1.23 machine prototype collection path.

The live 2.1.23 server rejected the adapter's original machine collection
with "LuaGameScript doesn't contain key entity_prototypes" and then, once
the prototype root was corrected, with "LuaEntityPrototype doesn't contain
key crafting_speed". Both failures were real and are fixed.

The tests execute the **real adapter Lua** against a mock that reproduces the
observed 2.1.23 runtime behaviour, so a regression is caught without a live
server:

* the prototype tables live under the runtime global ``prototypes``, and
  ``game.entity_prototypes`` does not exist at all;
* a prototype is a **userdata** object, not a table;
* reading an absent prototype member **raises** an error rather than
  returning nil;
* ``crafting_categories`` is a **dictionary** of category name to boolean;
* ``allowed_effects`` and ``allowed_module_categories`` are dictionaries;
* the fluid boxes are under ``fluidbox_prototypes``;
* the runtime prototype declares **no** ``crafting_speed`` attribute and
  **no** ``module_slots`` attribute; the crafting speed is reached through
  the **method** ``get_crafting_speed(quality?)`` and the module slot count
  through the **attribute** ``module_inventory_size``;
* ``get_crafting_speed`` is declared only on the ``CraftingMachine`` and
  ``Character`` subclasses, so a prototype without the method must be left
  without a speed instead of raising.

Every expected value here was observed on the live 2.1.23 server or read from
the pinned 2.1.23 API archive. Nothing is guessed.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"


def _adapter_source() -> str:
    return ADAPTER.read_text(encoding="utf-8")


def _machine_lua() -> str:
    """Return the adapter's machine-collection Lua block, de-indented.

    The block is taken verbatim from the adapter source, so the tests
    exercise the shipped code and not a copy of it. The adapter's Lua lives
    inside a C# raw string literal, so the literal's own indentation is
    removed before it is executed.
    """
    source = _adapter_source()
    start = source.index("local machines, machines_truncated = {}, false")
    end = source.index("local fingerprint", start)
    lines = source[start:end].split("\n")
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    trim = min(indents) if indents else 0
    return "\n".join(line[trim:] if len(line) >= trim else line
                     for line in lines)


def _code_lines() -> list[str]:
    """Return the adapter's Lua code lines, without the comments.

    The rejected prototype root may still be named in a comment that
    explains WHY it was rejected, so only executable lines are checked.
    """
    return [line for line in _adapter_source().split("\n")
            if not line.lstrip().startswith("--")]


#: A mock of the observed Factorio 2.1.23 runtime.
#:
#: ``__index`` raises for any name the prototype does not declare, which is
#: exactly how the live 2.1.23 runtime behaved: reading ``crafting_speed``
#: produced "LuaEntityPrototype doesn't contain key crafting_speed".
MOCK_RUNTIME = """
local function prototype(fields, methods)
  return setmetatable({}, {
    __index = function(_, key)
      local value = fields[key]
      if value ~= nil then return value end
      local method = methods and methods[key]
      if method ~= nil then return method end
      error("LuaEntityPrototype doesn't contain key " .. tostring(key), 2)
    end,
  })
end

local function box(fields)
  return setmetatable({}, {
    __index = function(_, key)
      local value = fields[key]
      if value == nil then
        error("LuaFluidBoxPrototype doesn't contain key " .. tostring(key), 2)
      end
      return value
    end,
  })
end

-- The mock prototypes: one assembling machine, one furnace, and one
-- prototype that is not a machine at all.
--
-- The pinned 2.1.23 runtime archive declares the crafting speed on
-- LuaEntityPrototype as the METHOD get_crafting_speed(quality?), and it
-- restricts that method to the CraftingMachine and Character subclasses.
-- The assembling machine therefore declares the method and the furnace
-- does not, so the adapter must call it only where it exists.
local entity = {
  ["assembling-machine-1"] = prototype({
    crafting_categories = {crafting = true},
    energy_usage = 1250,
    allowed_effects = {consumption = true, speed = true},
    allowed_module_categories = {speed = true, productivity = true},
    fluidbox_prototypes = {
      box({production_type = "input", index = 1}),
      box({production_type = "output", index = 2}),
    },
    module_inventory_size = 2,
    quality_affects_module_slots = true,
    crafting_speed_quality_multiplier = {normal = 1.0, uncommon = 1.5},
    size = {x = 3, y = 3},
    direction = {0, 2, 4, 6},
    type = "assembling-machine",
    name = "assembling-machine-1",
  }, {
    get_crafting_speed = function(...)
      assert(select('#', ...) == 0, 'bound method got a receiver')
      return 0.75
    end,
  }),
  ["stone-furnace"] = prototype({
    crafting_categories = {smelting = true},
    energy_usage = 1500,
    allowed_effects = {speed = true},
    allowed_module_categories = {speed = true},
    fluidbox_prototypes = {},
    size = {x = 2, y = 2},
    direction = {0, 2, 4, 6},
    type = "furnace",
    name = "stone-furnace",
  }),
  -- A machine whose prototype declares no size at all. The adapter must
  -- report it without a footprint rather than invent one.
  ["sizeless-machine"] = prototype({
    crafting_categories = {crafting = true},
    energy_usage = 1000,
    fluidbox_prototypes = {},
    type = "assembling-machine",
    name = "sizeless-machine",
  }),
  ["tree-1"] = prototype({type = "tree", name = "tree-1"}),
}

-- The observed 2.1.23 runtime global.
prototypes = {entity = entity, item = {}, recipe = {}}

-- The observed 2.1.23 runtime has NO game.entity_prototypes. Any access
-- must fail loudly, exactly as the live server did.
game = setmetatable({}, {
  __index = function(_, key)
    error("LuaGameScript doesn't contain key " .. tostring(key), 2)
  end,
})
-- A minimal JSON encoder, so the Python side receives plain data. A nil
-- value is written as null, which is how an absent crafting speed or
-- energy appears in the reported row.
local function encode(value)
  if value == nil then return "null" end
  local kind = type(value)
  if kind == "number" or kind == "boolean" then return tostring(value) end
  if kind == "string" then
    return '"' .. value:gsub('\\\\', '\\\\\\\\'):gsub('"', '\\\\"') .. '"'
  end
  if kind ~= "table" then return "null" end
  local count, is_array = 0, true
  for key in pairs(value) do
    count = count + 1
    if type(key) ~= "number" then is_array = false end
  end
  local parts = {}
  if is_array and count == #value then
    for _, item in ipairs(value) do parts[#parts+1] = encode(item) end
    return "[" .. table.concat(parts, ",") .. "]"
  end
  for key, item in pairs(value) do
    parts[#parts+1] = '"' .. tostring(key) .. '":' .. encode(item)
  end
  return "{" .. table.concat(parts, ",") .. "}"
end
helpers = {json_encode = encode}
"""


class MachinePrototypePathTests(unittest.TestCase):
    """The machine collection must read the declared 2.1.23 runtime path."""

    def test_the_adapter_no_longer_reads_game_entity_prototypes(self):
        """The rejected prototype root must be gone from the adapter code."""
        offending = [line for line in _code_lines()
                     if "game.entity_prototypes" in line]
        self.assertEqual(offending, [])

    def test_the_adapter_reads_the_prototypes_global(self):
        """The adapter must read the declared ``prototypes.entity`` table."""
        self.assertIn("prototypes.entity", _adapter_source())

    def test_the_lua_block_uses_the_prototypes_global(self):
        """The machine block itself must not use the rejected root."""
        block = _machine_lua()
        offending = [line for line in block.split("\n")
                     if "game.entity_prototypes" in line
                     and not line.lstrip().startswith("--")]
        self.assertEqual(offending, [])


class MachineCollectionExecutionTests(unittest.TestCase):
    """Execute the real adapter machine collection against the mock runtime."""

    def setUp(self):
        try:
            import lupa  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("lupa is not installed; the Lua contract cannot run")

    def collect(self) -> list[dict[str, Any]]:
        """Run the adapter's machine collection and return the rows.

        The rows are returned as JSON so the Python side sees plain data
        with no Lua table semantics.
        """
        import lupa

        program = (
            MOCK_RUNTIME
            + "\n"
            + _machine_lua()
            + "\n"
            + "local out = {} "
            + "for _, row in ipairs(machines) do "
            + "  local entry = {name=row.name} "
            + "  entry.crafting_categories = row.crafting_categories "
            + "  entry.crafting_speed = row.crafting_speed "
            + "  entry.energy_usage = row.energy_usage "
            + "  entry.allowed_effects = row.allowed_effects "
            + "  entry.allowed_module_categories = row.allowed_module_categories "
            + "  entry.module_slots = row.module_slots "
            + "  entry.quality_affects_module_slots = row.quality_affects_module_slots "
            + "  entry.crafting_speed_quality_multiplier = row.crafting_speed_quality_multiplier "
            + "  entry.size = row.size "
            + "  entry.directions = row.directions "
            + "  local boxes = {} "
            + "  for _, box in ipairs(row.fluid_boxes or {}) do "
            + "    boxes[#boxes+1] = {production_type=box.production_type} end "
            + "  entry.fluid_boxes = boxes "
            + "  out[#out+1] = entry end "
            + "return helpers.json_encode(out)\n"
        )
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        result = lua.execute(program)
        rows = json.loads(str(result))
        return sorted(rows, key=lambda item: item["name"])

    def test_the_collection_reads_the_prototypes_without_error(self):
        """The collection must not raise against the observed runtime.

        This is the regression for the live failure "LuaGameScript doesn't
        contain key entity_prototypes".
        """
        self.assertTrue(self.collect())

    def test_only_the_machines_are_reported(self):
        """A prototype with no crafting category is not a machine."""
        names = [row["name"] for row in self.collect()]
        self.assertIn("assembling-machine-1", names)
        self.assertIn("stone-furnace", names)
        self.assertNotIn("tree-1", names)

    def test_the_dictionary_categories_are_reported(self):
        """``crafting_categories`` is a dictionary, so its keys are the categories."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["crafting_categories"],
                         ["crafting"])
        self.assertEqual(rows["stone-furnace"]["crafting_categories"],
                         ["smelting"])

    def test_a_machine_without_an_observed_speed_is_still_reported(self):
        """A prototype without the speed method is reported without a speed.

        The pinned 2.1.23 archive restricts ``get_crafting_speed`` to the
        ``CraftingMachine`` and ``Character`` subclasses, so a prototype
        that does not declare the method must still be visible and must
        carry no speed at all. The planner refuses to invent one.
        """
        rows = {row["name"]: row for row in self.collect()}
        self.assertIn("stone-furnace", rows)
        # A Lua nil member does not exist in the table, so the reported row
        # carries no crafting_speed at all.
        self.assertNotIn("crafting_speed", rows["stone-furnace"])

    def test_the_crafting_speed_is_read_through_the_declared_method(self):
        """The speed comes from ``get_crafting_speed``, not from a member.

        The pinned 2.1.23 archive declares no ``crafting_speed`` attribute
        on ``LuaEntityPrototype``; the declared accessor is the method
        ``get_crafting_speed(quality?)``. Reading the attribute directly
        raised "doesn't contain key crafting_speed" on the live server.
        """
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["crafting_speed"], 0.75)

    def test_the_module_slot_count_is_read_from_the_declared_attribute(self):
        """``module_inventory_size`` is the declared normal-quality count."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["module_slots"], 2)

    def test_a_machine_without_module_support_reports_no_slots(self):
        """A machine with no module inventory reports no slot count."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertNotIn("module_slots", rows["stone-furnace"])

    def test_the_quality_information_is_reported(self):
        """The quality-dependent speed and slot information is reported."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertTrue(
            rows["assembling-machine-1"]["quality_affects_module_slots"])
        self.assertEqual(
            rows["assembling-machine-1"]["crafting_speed_quality_multiplier"],
            {"normal": 1.0, "uncommon": 1.5})

    def test_the_observed_energy_is_reported(self):
        """Runtime J/tick is normalized to watts at the adapter boundary."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["energy_usage"], 75000)
        self.assertEqual(rows["stone-furnace"]["energy_usage"], 90000)

    def test_the_dictionary_allowed_effects_are_reported(self):
        """``allowed_effects`` is a dictionary, so the enabled keys are reported."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["allowed_effects"],
                         ["consumption", "speed"])
        self.assertEqual(rows["stone-furnace"]["allowed_effects"], ["speed"])

    def test_the_dictionary_allowed_module_categories_are_reported(self):
        """``allowed_module_categories`` is a dictionary too."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["allowed_module_categories"],
                         ["productivity", "speed"])

    def test_the_fluid_boxes_come_from_the_declared_field(self):
        """The fluid boxes are read from ``fluidbox_prototypes``."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(
            rows["assembling-machine-1"]["fluid_boxes"],
            [{"production_type": "input"}, {"production_type": "output"}])

    def test_a_machine_without_fluid_boxes_reports_none(self):
        """A machine with an empty fluid box list reports an empty list."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["stone-furnace"]["fluid_boxes"], [])

    def test_the_observed_size_is_reported(self):
        """The machine footprint is read from the observed prototype size."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["size"],
                         {"width": 3, "height": 3})
        self.assertEqual(rows["stone-furnace"]["size"],
                         {"width": 2, "height": 2})

    def test_the_supported_directions_are_reported(self):
        """The supported orientations are read from the observed prototype."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertEqual(rows["assembling-machine-1"]["directions"], [0, 2, 4, 6])

    def test_a_machine_without_an_observed_size_reports_none(self):
        """A prototype without a usable size reports no size at all."""
        rows = {row["name"]: row for row in self.collect()}
        self.assertIn("sizeless-machine", rows)
        self.assertIsNone(rows["sizeless-machine"].get("size"))


class MachineRowShapeTests(unittest.TestCase):
    """The reported machine rows must match the Python validator's contract."""

    def validate(self, machine: dict[str, Any]) -> list[dict[str, Any]]:
        import sys

        sys.path.insert(0, str(ROOT / "agent"))
        from read_only_planning import validate_machines

        return validate_machines({"machines": [machine]})

    def test_the_validator_accepts_a_machine_without_a_speed(self):
        """A machine with an unknown speed must still validate.

        The Python validator reads ``crafting_speed`` with a helper that
        yields None for a missing value. The machine must survive
        validation so the planner can see it and refuse to plan it.
        """
        machines = self.validate({
            "name": "assembling-machine-1",
            "crafting_categories": ["crafting"],
            "energy_usage": 1250,
            "allowed_effects": ["consumption", "speed"],
            "allowed_module_categories": ["speed"],
            "fluid_boxes": [{"production_type": "input"}],
        })
        self.assertEqual(len(machines), 1)
        self.assertIsNone(machines[0]["crafting_speed"])
        self.assertEqual(machines[0]["energy_usage"], 1250)

    def test_the_validator_accepts_the_observed_footprint(self):
        """The observed size and directions must survive validation."""
        machines = self.validate({
            "name": "assembling-machine-1",
            "crafting_categories": ["crafting"],
            "energy_usage": 1250,
            "size": {"width": 3, "height": 3},
            "directions": [0, 2, 4, 6],
        })
        self.assertEqual(machines[0]["size"], {"width": 3, "height": 3})
        self.assertEqual(machines[0]["directions"], [0, 2, 4, 6])

    def test_the_validator_refuses_an_unusable_footprint(self):
        """A footprint the game did not report must not be defaulted."""
        for size in ({"width": 0, "height": 3}, {"width": 3.5, "height": 3},
                     {"width": 3, "height": 3, "depth": 1}, {"width": 3}):
            with self.assertRaises(ValueError):
                self.validate({
                    "name": "assembling-machine-1",
                    "crafting_categories": ["crafting"],
                    "energy_usage": 1250,
                    "size": size,
                })

    def test_the_validator_refuses_an_invalid_direction(self):
        """A direction outside the Factorio range must be refused."""
        with self.assertRaises(ValueError):
            self.validate({
                "name": "assembling-machine-1",
                "crafting_categories": ["crafting"],
                "energy_usage": 1250,
                "directions": [9],
            })

    def test_the_validator_refuses_an_invalid_speed(self):
        """A speed that is present but invalid is still refused."""
        with self.assertRaises(ValueError):
            self.validate({
                "name": "assembling-machine-1",
                "crafting_categories": ["crafting"],
                "crafting_speed": 0,
                "energy_usage": 1250,
            })

    def test_the_validator_still_refuses_an_unknown_field(self):
        """The machine contract must stay fail-closed for unknown fields."""
        with self.assertRaises(ValueError):
            self.validate({
                "name": "assembling-machine-1",
                "crafting_categories": ["crafting"],
                "energy_usage": 1250,
                "not_a_real_field": 1,
            })


class PinnedApiTests(unittest.TestCase):
    """The names the adapter uses must exist in the pinned 2.1.23 archive."""

    def setUp(self):
        self.api_path = (ROOT / ".local" / "factorio-api-offline" / "2.1.23"
                         / "files" / "runtime-api.json")
        if not self.api_path.is_file():
            self.skipTest("the pinned 2.1.23 API archive is not present")
        document = json.loads(self.api_path.read_text(encoding="utf-8"))
        classes = document["classes"]
        entries = (list(classes.values()) if isinstance(classes, dict)
                   else [c for c in classes if isinstance(c, dict)])
        self.attributes = {}
        self.methods = {}
        for entry in entries:
            attributes = entry.get("attributes") or []
            self.attributes[entry.get("name")] = {
                a.get("name") for a in attributes if isinstance(a, dict)}
            methods = entry.get("methods") or []
            self.methods[entry.get("name")] = {
                m.get("name"): m for m in methods if isinstance(m, dict)}

    def test_the_prototypes_global_is_the_declared_runtime_shape(self):
        """``LuaPrototypes.entity`` is the declared prototype table."""
        self.assertIn("entity", self.attributes["LuaPrototypes"])

    def test_the_declared_machine_fields_exist(self):
        """Every prototype field the adapter reads must be declared."""
        entity = self.attributes["LuaEntityPrototype"]
        for name in ("crafting_categories", "energy_usage", "allowed_effects",
                     "allowed_module_categories", "fluidbox_prototypes"):
            self.assertIn(name, entity)

    def test_the_prototype_declares_no_speed_and_no_module_slots(self):
        """The runtime prototype declares neither of them.

        The declared accessors are the method ``get_crafting_speed`` and the
        attribute ``module_inventory_size``, so a plain member read of
        ``crafting_speed`` or ``module_slots`` raises on the live server.
        """
        entity = self.attributes["LuaEntityPrototype"]
        self.assertNotIn("crafting_speed", entity)
        self.assertNotIn("module_slots", entity)

    def test_the_declared_speed_and_slot_accessors_exist(self):
        """The accessors the adapter uses must be declared.

        ``get_crafting_speed(quality?)`` and
        ``get_inventory_size(index, quality?)`` are **methods**; the module
        slot count and the quality rules are **attributes**.
        """
        entity = self.attributes["LuaEntityPrototype"]
        for name in ("module_inventory_size",
                     "crafting_speed_quality_multiplier",
                     "quality_affects_module_slots",
                     "module_slots_quality_bonus"):
            self.assertIn(name, entity)

    def test_the_declared_speed_accessor_is_a_method(self):
        """The crafting speed is reached through a method, not a member."""
        methods = self.methods["LuaEntityPrototype"]
        self.assertIn("get_crafting_speed", methods)
        self.assertIn("get_inventory_size", methods)
        signature = methods["get_crafting_speed"]
        self.assertEqual([p["name"] for p in signature["parameters"]],
                         ["quality"])
        self.assertTrue(signature["parameters"][0]["optional"])
        # The archive restricts the method to the crafting machines and the
        # character, so the adapter must not call it on any prototype.
        self.assertEqual(sorted(signature["subclasses"]),
                         ["Character", "CraftingMachine"])

    def test_the_game_script_declares_no_prototype_table(self):
        """``LuaGameScript`` has no prototype attribute at all.

        The live server rejected ``game.entity_prototypes`` for exactly this
        reason.
        """
        game = self.attributes["LuaGameScript"]
        self.assertFalse([name for name in game
                          if "proto" in str(name).lower()])


if __name__ == "__main__":
    unittest.main()
