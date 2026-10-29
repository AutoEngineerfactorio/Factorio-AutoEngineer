"""Offline proof of the R06 recipe accounting identity.

The R06 live report showed a **declared** recipe total, an **emitted** row
count and a difference between them, and it named only the exclusions that
travel with a single page. Those three numbers could not be reconciled,
because the adapter reports the exclusions **per page** while the declared
total is the **whole catalog**. A reader therefore saw a gap that no
exclusion accounted for.

This module executes the **real adapter Lua** against a mock force whose
exclusions are deliberately spread over several pages, and proves the
identity that the live numbers must satisfy:

    declared == emitted + excluded

where ``excluded`` is the union of the exclusions of **every** page and
``emitted`` is the union of the recipe rows of every page.

The mock reproduces the observed 2.1.23 runtime shape:

* ``force.recipes`` is a table of recipes;
* a recipe has ``enabled``, ``hidden``, ``energy``, ``category``,
  ``ingredients`` and ``products``;
* ``ingredients`` and ``products`` are **arrays** of parts;
* a part has ``name``, ``type`` and ``amount``;
* a product may carry ``independent_probability``,
  ``shared_probability`` and ``affected_by_quality``.

Nothing here is guessed: the shape is the one the live 2.1.23 server
exposes, and the accounting identity is the adapter's own contract.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"


def _adapter_source() -> str:
    return ADAPTER.read_text(encoding="utf-8")


def _catalog_lua() -> str:
    """Return the adapter's whole catalog Lua literal, de-indented.

    The literal is taken verbatim from the adapter source, so the test
    exercises the shipped code and not a copy of it. The adapter's Lua
    lives inside a C# raw string literal, so the literal's own indentation
    is removed before it is executed.
    """
    source = _adapter_source()
    start = source.index('$$$"""') + len('$$$"""')
    end = source.index('"""', start)
    block = source[start:end]
    # The literal contains C# raw-string interpolation placeholders;
    # replace them with the values the tests use so the Lua is directly
    # executable.
    block = block.replace("{{{pageSize}}}", "32")
    block = block.replace("{{{page}}}", "PAGE")
    # The catalogOnly placeholder is matched by shape rather than by a
    # hard-coded string, so the test does not depend on the exact
    # spelling of the C# expression.
    block = re.sub(r"\{\{\{\(catalogOnly[^\n]*?\}\}\}", "true", block)
    if "{{{" in block:
        remaining = sorted(set(re.findall(r"\{\{\{.*?\}\}\}", block)))
        raise AssertionError(
            f"an unresolved interpolation placeholder remains: {remaining}")
    lines = block.split("\n")
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    trim = min(indents) if indents else 0
    return "\n".join(line[trim:] if len(line) >= trim else line
                     for line in lines)


#: A mock of the observed Factorio 2.1.23 force.
#:
#: ``recipe`` builds one recipe. ``kind`` selects the shape that the
#: adapter is expected to reject, so the test can place an exclusion on a
#: chosen page.
MOCK_FORCE = """
local function part(name, amount)
  return {name = name, type = "item", amount = amount}
end

local function good_recipe(name)
  return {
    name = name,
    enabled = true,
    hidden = false,
    energy = 0.5,
    categories = {"crafting"},
    ingredients = {part("iron-plate", 1)},
    products = {part(name, 1)},
  }
end

-- A recipe whose products are not an array. The adapter checks the
-- product list before the recipe shape, so a product list that is not a
-- table is reported as "no_products".
local function bad_shape_recipe(name)
  return {
    name = name,
    enabled = true,
    hidden = false,
    energy = 0.5,
    categories = {"crafting"},
    ingredients = {part("iron-plate", 1)},
    products = "not-a-table",
  }
end

local recipes = {}
local names = {}
for i = 1, RECIPE_COUNT do
  local name = string.format("recipe-%04d", i)
  names[#names+1] = name
  if i == BAD_INDEX_1 or i == BAD_INDEX_2 then
    recipes[name] = bad_shape_recipe(name)
  else
    recipes[name] = good_recipe(name)
  end
end

local force = {
  name = "player",
  recipes = recipes,
  technologies = {},
}

-- The observed 2.1.23 runtime context the adapter's literal uses.
local surface = {name = "nauvis"}
local p = {force = force, surface = surface}
local c = {surface = surface}
local game = {tick = 1000}
local script = {active_mods = {base = "2.1.23"}}
local defines = {flow_precision_index = {ten_minutes = 60}}
local prototypes = {entity = {}, item = {}, recipe = {}}

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


class RecipeAccountingTests(unittest.TestCase):
    """The declared total must equal the emitted rows plus the exclusions."""

    def setUp(self):
        try:
            import lupa  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("lupa is not installed; the Lua contract cannot run")
        self.recipe_count = 100
        self.bad_index_1 = 10   # on page 1
        self.bad_index_2 = 70   # on page 3

    def page(self, page: int) -> dict[str, Any]:
        """Run the adapter's catalog block for one page and return it."""
        import lupa

        program = (
            f"RECIPE_COUNT = {self.recipe_count}\n"
            + f"BAD_INDEX_1 = {self.bad_index_1}\n"
            + f"BAD_INDEX_2 = {self.bad_index_2}\n"
            + "local PAGE = " + str(page) + "\n"
            + MOCK_FORCE
            + "\n"
            + _catalog_lua()
            + "\n"
            + "local out = {} "
            + "out.total = catalog_status and catalog_status.total_count "
            + "out.page = catalog_status and catalog_status.page "
            + "out.total_pages = catalog_status and catalog_status.total_pages "
            + "out.status = catalog_status and catalog_status.status "
            + "out.rows = capabilities and capabilities.recipes "
            + "out.excluded = capabilities and capabilities.excluded "
            + "out.truncated = capabilities and capabilities.truncated "
            + "return helpers.json_encode(out)\n"
        )
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        raw = lua.execute(program)
        return json.loads(str(raw))

    def all_pages(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """Return (emitted rows, exclusions, declared total) for every page."""
        first = self.page(1)
        declared = first["total"]
        total_pages = first["total_pages"]
        rows = list(first["rows"] or [])
        excluded = list(first["excluded"] or [])
        for page in range(2, total_pages + 1):
            payload = self.page(page)
            rows.extend(payload["rows"] or [])
            excluded.extend(payload["excluded"] or [])
        return rows, excluded, declared

    def test_the_declared_total_is_the_whole_catalog(self):
        """``total_count`` counts every recipe, not only the page's rows."""
        first = self.page(1)
        self.assertEqual(first["total"], self.recipe_count)
        self.assertEqual(first["page"], 1)
        self.assertEqual(first["total_pages"], 4)

    def test_the_exclusions_travel_with_their_own_page(self):
        """Each page reports only the exclusions of its own recipes.

        This is the behaviour that made the live numbers impossible to
        reconcile: a single page's exclusions were compared against the
        whole catalog's declared total.
        """
        first = self.page(1)
        self.assertEqual(len(first["excluded"]), 1)
        self.assertEqual(first["excluded"][0]["reason"], "no_products")
        third = self.page(3)
        self.assertEqual(len(third["excluded"]), 1)
        self.assertNotEqual(first["excluded"][0]["name"],
                            third["excluded"][0]["name"])
        second = self.page(2)
        self.assertEqual(second["excluded"], [])

    def test_the_accounting_identity_holds_over_every_page(self):
        """declared == emitted + excluded, with no unexplained remainder.

        This is the reconciliation the R06 report could not produce.
        """
        rows, excluded, declared = self.all_pages()
        self.assertEqual(len(rows), self.recipe_count - len(excluded))
        self.assertEqual(len(excluded), 2)
        self.assertEqual(len(rows) + len(excluded), declared)
        # Every excluded recipe is named exactly once.
        excluded_names = [entry["name"] for entry in excluded]
        self.assertEqual(len(set(excluded_names)), len(excluded_names))
        # Every emitted row is a real recipe and no recipe is emitted twice.
        emitted_names = [row["name"] for row in rows]
        self.assertEqual(len(set(emitted_names)), len(emitted_names))
        self.assertEqual(len(set(emitted_names) | set(excluded_names)),
                         self.recipe_count)

    def test_a_single_page_cannot_reconcile_the_whole_catalog(self):
        """One page's rows and exclusions never cover the declared total.

        This is the arithmetic that produced the unexplained 679: a
        partial picture compared against the whole catalog's total.
        """
        first = self.page(1)
        page_rows = len(first["rows"] or [])
        page_excluded = len(first["excluded"] or [])
        self.assertLess(page_rows + page_excluded, first["total"])

    def test_the_exclusion_reason_is_the_observed_one(self):
        """A product list that is not a table is reported as ``no_products``.

        The adapter checks the product list before the recipe shape, so the
        reason is the one that was actually observed and never a guess.
        """
        _, excluded, _ = self.all_pages()
        self.assertEqual({entry["reason"] for entry in excluded},
                         {"no_products"})


class AccountingContractTests(unittest.TestCase):
    """The adapter source must keep the per-page exclusion contract."""

    def test_the_exclusion_list_is_built_inside_the_page_loop(self):
        """The exclusions must be scoped to the page's recipe range.

        ``local excluded = {}`` has to sit inside the page branch, next to
        the ``for i=first,last`` loop, so that a page reports its own
        exclusions. A catalogue-wide exclusion list would have to gather
        every recipe and would defeat the bounded page read.
        """
        source = _adapter_source()
        excluded_at = source.index("local excluded = {}")
        loop_at = source.index("for i=first,last do")
        self.assertLess(excluded_at, loop_at)
        # The page range is what bounds the loop.
        self.assertIn("local first = ({{{page}}} - 1) * {{{pageSize}}} + 1",
                      source)
        self.assertIn("local last = math.min(first + {{{pageSize}}} - 1, total)",
                      source)

    def test_the_total_counts_every_recipe_name(self):
        """The declared total is the length of the whole recipe name list."""
        source = _adapter_source()
        self.assertIn("local total, total_pages = #recipe_names,", source)


if __name__ == "__main__":
    unittest.main()
