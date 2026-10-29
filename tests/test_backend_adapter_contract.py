import re
import unittest
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
MOD = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
#: The observation runs inside the mod now. The entity observation and the
#: catalog observation are two separate modules.
MOD_MAP = MOD / "observation_map.lua"
MOD_CAPABILITIES = MOD / "observation_capabilities.lua"
MOD_CATALOG = MOD / "observation_catalog.lua"
MOD_TELEMETRY = MOD / "observation_telemetry.lua"


class NatureObservationContractTests(unittest.TestCase):
    """The read-only observer must report what the map layer needs, and only that.

    The observation runs inside the ``autoengineer-input`` mod, so these
    assertions pin the mod's Lua. The behaviour they protect is unchanged:
    the same entity kinds, the same chart colours, the same identity and
    direction fields and the same bounded collection.
    """

    def setUp(self):
        self.tools = (ROOT / "backend-safety" / "AutoEngineerTools.cs").read_text(
            encoding="utf-8"
        )
        self.patch = PATCH.read_text(encoding="utf-8")
        self.observer = MOD_MAP.read_text(encoding="utf-8")

    def test_the_nature_filter_includes_cliffs(self):
        # Factorio 2.1.23 cliffs have the entity type "cliff"; the previous
        # filter only listed trees and simple entities, so no cliff was ever
        # observed.
        self.assertIn('{ kind = "nature", types = { "tree", "simple-entity", "cliff" } }',
                      self.observer)

    def test_the_observer_reports_the_prototype_chart_colour(self):
        self.assertIn("friendly_map_color", self.observer)
        self.assertIn("enemy_map_color", self.observer)
        self.assertIn("map_color", self.observer)
        self.assertIn("record.map_color = color", self.observer)

    def test_the_chart_colour_prefers_the_force_specific_colour(self):
        # The 2.1.23 runtime API documents map_color as the colour used "if a
        # friendly or enemy color isn't defined", so the force-specific colour
        # is the one the game charts with.
        self.assertIn('{ "friendly_map_color", "map_color" }', self.observer)
        self.assertIn('{ "enemy_map_color", "map_color" }', self.observer)

    def test_the_observer_reports_the_entity_and_prototype_type(self):
        self.assertIn("record.entity_type = entity.type", self.observer)
        self.assertIn("record.prototype_type = prototype_type", self.observer)

    def test_the_observer_reports_the_observed_direction(self):
        self.assertIn("record.direction = direction", self.observer)

    def test_the_nature_observation_payload_stays_bounded(self):
        # Nature collection is partitioned by bounded chunks.  The old single
        # 512-entity window allowed one dense forest to exhaust the visible
        # budget before less dense areas were visited.
        self.assertIn("MAP_CHUNK_TILES = 64", self.observer)
        self.assertIn("MAP_CHUNK_ENTITY_BUDGET = 2048", self.observer)
        self.assertIn("MAP_CHUNK_WINDOW_TILES = 32", self.observer)
        self.assertIn("map_chunk", self.observer)
        self.assertIn("partial = partial", self.observer)
        self.assertIn("r = math.floor", self.observer)
        self.assertIn("g = math.floor", self.observer)
        self.assertIn("b = math.floor", self.observer)

    def test_the_observer_checks_visibility_after_chunk_collection(self):
        # find_entities_filtered applies its limit before Lua receives the
        # rows, so a chunk must be explicit and its result marked partial
        # rather than silently presenting a dense forest as complete.
        self.assertIn("chunk_complete", self.observer)
        self.assertIn("#part > MAP_CHUNK_ENTITY_LIMIT", self.observer)
        self.assertIn("#found >= MAP_CHUNK_ENTITY_BUDGET", self.observer)

    def test_the_nature_observation_adds_no_gameplay_command(self):
        # The observer stays read-only: no charting, no world mutation.
        for content in (self.observer, self.tools):
            self.assertNotIn("surface.create_entity", content)
            self.assertNotIn("surface.chart(", content)
            self.assertNotIn("player.teleport", content)
            self.assertNotIn("game.command", content)

    def test_the_restricted_tool_boundary_is_unchanged(self):
        # The Allowed dictionary includes the new bounded read-only telemetry
        # and inventory tools, without adding any new gameplay write
        # capabilities. The count is pinned so that a further tool cannot be
        # added silently.
        start = self.tools.index("internal static readonly Dictionary<string, string[]> Allowed")
        end = self.tools.index("};", start)
        allowed = self.tools[start:end]
        names = re.findall(r'\["([a-z_]+)"\]\s*=', allowed)
        self.assertEqual(len(names), 14)
        self.assertEqual(len(set(names)), 14)
        self.assertIn("autoengineer_telemetry", names)
        self.assertIn("autoengineer_inventory", names)
        for name in (
            "autoengineer_operation_preview",
            "autoengineer_operation",
            "autoengineer_view",
            "autoengineer_policy",
            "get_player_position",
            "scan_resources",
            "get_nearby_entities",
            "walk_to_position",
            "autoengineer_status",
            "autoengineer_arm",
            "autoengineer_renew",
            "autoengineer_stop",
        ):
            self.assertIn(name, names)

    def test_the_fast_view_mode_is_an_allowed_argument(self):
        """``noCatalog`` must be an allowed argument of the view tool.

        The dispatch filter rejects any argument key that is not declared
        for the tool, so the fast mode has to be declared here or it can
        never be used.
        """
        start = self.tools.index('["autoengineer_view"]')
        end = self.tools.index("],", start)
        arguments = re.findall(r'"([A-Za-z]+)"', self.tools[start:end])
        self.assertIn("noCatalog", arguments)
        self.assertIn("catalogOnly", arguments)
        # The fast mode adds no new tool, so the boundary stays at 13.
        self.assertEqual(len(set(arguments)), len(arguments))


class RecipeResearchAdapterContractTests(unittest.TestCase):
    def test_adapter_uses_factorio_active_base_version(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn('local game_version = script.active_mods["base"]', source)
        self.assertIn("type(game_version) ~= \"string\"", source)
        self.assertIn("game_version=game_version", source)
        self.assertNotIn("game.version", source)

    def test_combined_patch_contains_same_version_contract(self):
        patch = PATCH.read_text(encoding="utf-8")
        self.assertIn('+                local game_version = script.active_mods["base"]', patch)
        self.assertIn("+                    hash_text(game_version)", patch)
        self.assertIn("+                            schema=1,game_version=game_version,", patch)
        self.assertNotIn("+                    hash_text(game.version)", patch)
        self.assertNotIn("game_version=game.version", patch)

    def test_adapter_and_combined_patch_include_bounded_technology_unlocks(self):
        source = ADAPTER.read_text(encoding="utf-8")
        patch = PATCH.read_text(encoding="utf-8")
        for content in (source, patch):
            self.assertIn("technology.prototype.effects", content)
            self.assertIn('effect.type == "unlock-recipe"', content)
            self.assertIn("unlock_data_truncated", content)
            self.assertIn("unlock_technologies=unlock_by_recipe[name] or {}", content)
            self.assertIn("effect_count > 50000", content)

    def test_adapter_and_combined_patch_include_read_only_telemetry(self):
        """The telemetry observation reads production and power, and writes nothing.

        The observation now lives in the mod's ``observation_telemetry`` module,
        so the assertions follow it there. The behaviour is unchanged: the
        item and fluid production statistics and the electric network flow.
        """
        telemetry = MOD_TELEMETRY.read_text(encoding="utf-8")
        self.assertIn("get_item_production_statistics", telemetry)
        self.assertIn("get_fluid_production_statistics", telemetry)
        # The production windows are the one-minute and the five-second rate.
        self.assertIn("one_minute", telemetry)
        self.assertIn("five_seconds", telemetry)
        self.assertIn("per_second_produced", telemetry)
        self.assertIn("maximum_production", telemetry)
        self.assertIn("joules_per_tick", telemetry)
        # The observation never writes to the game.
        for forbidden in ("create_entity", "chart(", "teleport", "add_research",
                          "surface.set_tiles"):
            self.assertNotIn(forbidden, telemetry)
        # The backend routes it over the registered mod command.
        tools = (ROOT / "backend-safety" / "AutoEngineerTools.cs").read_text(encoding="utf-8")
        self.assertIn('ModObservation.BuildCommand("telemetry")', tools)
        self.assertNotIn("ExecuteLuaAsync", tools)

    def test_telemetry_status_transition_clears_stale_unavailable_reason(self):
        source = ADAPTER.read_text(encoding="utf-8")
        # An available response must not inherit the initially unavailable reason.
        self.assertIn(
            'telemetry.production.status = "ok"\n'
            '                    telemetry.production.reason = nil',
            source,
        )
        # A genuine partial/unavailable response must retain an accurate explanation.
        self.assertIn(
            'telemetry.production.status = "partial"\n'
            '                        telemetry.production.reason = '
            '"Active history cap reached or one flow type unavailable"',
            source,
        )
        self.assertIn(
            'telemetry.production.status = "unavailable"\n'
            '                    telemetry.production.reason = "Production statistics unavailable"',
            source,
        )

    def test_adapter_uses_instantaneous_21_power_and_drops_20_fallback(self):
        """Factorio 2.1.23 is the only supported target, so the adapter must use
        the instantaneous LuaElectricNetwork API and must no longer carry the
        archived Factorio 2.0 historical-statistics fallback."""
        source = ADAPTER.read_text(encoding="utf-8")
        patch = PATCH.read_text(encoding="utf-8")
        for body in (source, patch):
            self.assertIn("pole.electric_network", body)
            self.assertIn("parent.flow_last_tick", body)
            self.assertIn("maximum_production", body)
            self.assertIn("consumption_satisfaction", body)
            self.assertIn('status=#networks==0 and "unavailable" or "ok"', body)
            self.assertIn("partial=partial}", body)
            # The archived 2.0 branch must be gone from the active adapter.
            self.assertNotIn("legacy_20", body)
            self.assertNotIn("legacy_statistics", body)
            self.assertNotIn("electric_network_statistics", body)
            self.assertNotIn('match("^2%.0%.")', body)

    def test_adapter_accepts_factorio_21_product_quality_and_probability_fields(self):
        """Factorio 2.1 products carry quality/probability keys; they must be
        accepted for products with bounded values, never for ingredients, and
        unknown fields must still be rejected."""
        source = ADAPTER.read_text(encoding="utf-8")
        # The product-only allowance is explicit and bounded.
        self.assertIn('local function normalized_parts(source, limit, is_product)', source)
        self.assertIn('elseif field == "affected_by_quality" then', source)
        # Observed 2.1.23 shapes: independent_probability is a number in 0..1 and
        # shared_probability is a {min,max} table, not a number.
        self.assertIn('elseif field == "independent_probability" then', source)
        self.assertIn('elseif field == "shared_probability" then', source)
        self.assertIn('local low, high = value.min, value.max', source)
        # Unknown fields remain rejected.
        self.assertIn("else\n                                        return nil", source)
        # A product below certainty is not deterministic and must not be simple.
        self.assertIn("if value < 1 then deterministic = false end", source)
        self.assertIn("if high < 1 then deterministic = false end", source)
        self.assertIn("if part.deterministic == false then simple = false end", source)
        # Ingredients never receive the product-only fields.
        self.assertIn(
            "normalized_parts(recipe.ingredients, 16, false)", source
        )
        self.assertIn(
            "normalized_parts(recipe.products, 8, true)", source
        )

    def test_adapter_accepts_factorio_21_ingredient_flags_and_zero_amount_products(self):
        """Factorio 2.1 adds ingredient flags and allows a product amount of 0
        when the real yield comes from a probability."""
        source = ADAPTER.read_text(encoding="utf-8")
        # Known ingredient flags are accepted with bounded value types.
        self.assertIn('elseif field == "ignored_by_stats" then', source)
        self.assertIn('elseif field == "spoil_weight" then', source)
        self.assertIn(
            'elseif field == "fluidbox_multiplier" or field == "fluidbox_index" then', source
        )
        # A product may have amount 0; an ingredient must consume a positive amount.
        self.assertIn("if part.amount < 0 then return nil end", source)
        self.assertIn("if part.amount <= 0 then return nil end", source)
        # The quality and probability fields stay product-only.
        self.assertIn("if not is_product then return nil end", source)

    def test_adapter_keeps_multi_category_recipes_with_bounded_categories(self):
        """Factorio 2.1 recipes may declare several categories. The row must be
        kept, the primary category reported, and the full list bounded."""
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn("local categories = {}", source)
        self.assertIn("math.min(#category_list, 8)", source)
        self.assertIn("and categories[1] or nil", source)
        self.assertIn("category=category,categories=categories,", source)

    def test_patch_embeds_exact_readable_adapter_source(self):
        patch = PATCH.read_text(encoding="utf-8")
        for path, source_path in (
            (
                "FactorioMCP/Tools/RecipeResearchAdapter.cs",
                ADAPTER,
            ),
            (
                "FactorioMCP/Tools/AutoEngineerTools.cs",
                ROOT / "backend-safety" / "AutoEngineerTools.cs",
            ),
        ):
            with self.subTest(path=path):
                source = source_path.read_text(encoding="utf-8").splitlines()
                marker = patch.index(f"+++ b/{path}")
                hunk_start = patch.index("@@ -0,0 +1,", marker)
                hunk_end = patch.find("\n--- /dev/null", hunk_start)
                if hunk_end < 0:
                    hunk_end = patch.find("\ndiff --git ", hunk_start)
                if hunk_end < 0:
                    hunk_end = len(patch)
                hunk = patch[hunk_start:hunk_end].splitlines()
                added = [line[1:] for line in hunk[1:] if line.startswith("+")]
                declared_count = int(hunk[0].split("+1,", 1)[1].split(" ", 1)[0])

                self.assertEqual(declared_count, len(added))
                self.assertEqual(added, source)


class FastViewPathContractTests(unittest.TestCase):
    """The fast view path must not read the recipe catalog.

    The catalog enumerates every recipe, recomputes the technology
    fingerprint and enumerates every machine prototype. At the observed
    live Pyanodons scale that is 10,146 recipes to emit one page of 32,
    measured offline at 165.5 ms of Lua per call, and the dashboard polls
    the view once a second.

    The fast path therefore asks the mod only for the status and the
    inventory. It must not request the catalog, the terrain, the entities
    or the overlays.
    """

    def setUp(self):
        self.tools = (ROOT / "backend-safety" / "AutoEngineerTools.cs").read_text(
            encoding="utf-8"
        )
        self.composer = (ROOT / "backend-safety" / "Tools" / "ViewComposer.cs").read_text(
            encoding="utf-8"
        )

    def test_the_fast_path_omits_the_catalog(self):
        """The fast path asks the mod for the status and the inventory only."""
        self.assertIn("noCatalog", self.tools)
        start = self.composer.index("public async Task<string> ComposeFast(")
        end = self.composer.index("public async Task<string> ComposeMap(")
        fast = self.composer[start:end]
        self.assertIn('"status"', fast)
        self.assertIn('"inventory"', fast)
        for observation in ('"terrain"', '"map"', '"overlay"', '"recipes"',
                            '"research"', '"capabilities"'):
            self.assertNotIn(observation, fast)

    def test_the_fast_path_does_not_call_the_adapter_builder(self):
        """The adapter builder must not run on the fast path."""
        self.assertNotIn("RecipeResearchAdapter", self.tools)
        self.assertNotIn("RecipeResearchAdapter", self.composer)

    def test_every_operation_the_view_uses_is_allowed(self):
        """The backend allowlist must cover every operation the view asks for.

        ``ModObservation.BuildCommand`` refuses an operation that is not in
        ``AllowedOperations``. A view that asks for an operation the
        allowlist forgot therefore fails closed and the dashboard shows
        nothing at all. The live failure was exactly that: the allowlist
        had no ``inventory``, ``terrain`` or ``overlay``.
        """
        observation = (ROOT / "backend-safety" / "Tools" / "ModObservation.cs").read_text(
            encoding="utf-8"
        )
        allowed_start = observation.index("AllowedOperations")
        allowed_end = observation.index("};", allowed_start)
        allowed = observation[allowed_start:allowed_end]
        for selector in ("status", "telemetry", "map", "terrain", "overlay",
                         "inventory", "recipes", "research", "machines",
                         "capabilities", "machine_inventories", "logistics",
                         "robots", "transport"):
            self.assertIn(f'"{selector}"', allowed,
                          f"{selector} must be an allowed observation")
        # The composer asks for these; each one must be allowed.
        for selector in ("status", "inventory", "terrain", "map", "overlay",
                         "capabilities", "machine_inventories",
                         "logistics", "robots", "transport"):
            self.assertIn(f'rcon, "{selector}"', self.composer)

    def test_the_backend_allowlist_matches_the_mod_request_parser(self):
        """The backend and the mod must accept the same operation names.

        The R10-A drift was exactly this: the mod's parser accepted
        ``inventory``, ``terrain`` and ``overlay`` while the backend
        allowlist did not, so every view failed closed with an opaque
        error. The lists are compared **as sets derived from the source**,
        so a new operation that is added to one side and forgotten on the
        other fails here instead of in a live game.
        """
        parse = (ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
                 / "observation_parse.lua").read_text(encoding="utf-8")
        operations_start = parse.index("parse.OPERATIONS")
        operations_end = parse.index("}", operations_start)
        operations = parse[operations_start:operations_end]
        mod_operations = set(re.findall(r"(\w+)\s*=\s*true", operations))

        observation = (ROOT / "backend-safety" / "Tools" / "ModObservation.cs").read_text(
            encoding="utf-8"
        )
        allowed_start = observation.index("AllowedOperations")
        allowed_end = observation.index("};", allowed_start)
        allowed = observation[allowed_start:allowed_end]
        backend_operations = set(re.findall(r'"(\w+)"', allowed))

        self.assertTrue(mod_operations, "the mod parser declares no operation")
        self.assertEqual(
            backend_operations, mod_operations,
            "the backend allowlist and the mod request parser disagree; "
            "an operation that one side accepts and the other refuses "
            "fails closed with an opaque error",
        )

    def test_the_inventory_observations_are_not_part_of_the_fast_path(self):
        """The expensive inventory observations must stay off the fast path.

        The fast path is polled every second. Reading the machine
        inventories and the logistic networks walks entities, so they may
        only ever be requested on demand.
        """
        fast_start = self.composer.index("ComposeFast")
        fast_end = self.composer.index("ComposeMap", fast_start)
        fast = self.composer[fast_start:fast_end]
        for selector in ("machine_inventories", "logistics", "robots",
                         "transport"):
            self.assertNotIn(f'rcon, "{selector}"', fast,
                             f"{selector} must not run on the fast path")

    def test_the_view_tool_reports_a_safe_diagnostic_instead_of_failing(self):
        """A failed view must be a truthful unavailable frame, not an error.

        Without the guard the MCP SDK reported the generic
        "An error occurred invoking 'autoengineer_view'." and the dashboard
        could not tell an unavailable observation from a broken backend.
        """
        self.assertIn("view_transport_failed", self.tools)
        self.assertIn("error_type", self.tools)
        # The diagnostic payload must not carry the RCON command, a credential
        # or the exception text itself. Only the exception *type* is exposed.
        start = self.tools.index("reason = \"view_transport_failed\"")
        end = self.tools.index("});", start)
        payload = self.tools[start:end]
        self.assertIn("error_type = ex.GetType().Name", payload)
        for forbidden in ("ex.Message", "ex.ToString()", "password",
                          "FACTORIO_RCON"):
            self.assertNotIn(forbidden, payload)

    def test_a_catalog_read_cannot_suppress_the_catalog(self):
        """``catalogOnly`` and ``noCatalog`` together are refused.

        A catalog read that also suppressed the catalog would report an
        empty catalog, which is indistinguishable from a catalog that
        genuinely has no recipes.
        """
        self.assertIn(
            'throw new ArgumentException("A catalog read cannot also suppress the catalog")',
            self.tools)

    def test_the_catalog_read_path_asks_the_mod_for_the_catalog(self):
        """The catalog-only path asks the mod for one bounded catalog page."""
        self.assertIn("ComposeCatalog(", self.tools)
        start = self.composer.index("public async Task<string> ComposeCatalog(")
        end = self.composer.index("private static string Frame(", start)
        catalog = self.composer[start:end]
        self.assertIn('rcon, "capabilities"', catalog)
        self.assertIn('frame["capabilities"] = rich', catalog)
        self.assertIn('frame["catalog_status"] = ReadObject(catalog, "catalog_status")', catalog)
        for observation in ('"terrain"', '"map"', '"overlay"'):
            self.assertNotIn(observation, catalog)

    def test_the_fast_path_reports_the_catalog_fields_as_absent(self):
        """The fast frame carries no catalog fields at all.

        The absent value is what tells the dashboard that no catalog was
        read, so the fast frame must not carry an empty or stale one.
        """
        start = self.composer.index("private static string Frame(")
        end = self.composer.index("private static Dictionary<string, object?> ComposeTerrain(")
        frame = self.composer[start:end]
        self.assertNotIn("capabilities", frame)
        self.assertNotIn("catalog_status", frame)

    def test_the_fast_path_adds_no_gameplay_capability(self):
        """The fast path is a read that stays inside the restricted set."""
        for forbidden in ("game.command", "player.teleport", "surface.chart(",
                          "surface.create", "remote.call"):
            self.assertNotIn(forbidden, self.composer)


class ChunkEntityBudgetContractTests(unittest.TestCase):
    """The chunk-level completeness signal must use the merged entity count.

    The observer reads one aligned 64x64 map chunk as four 32x32
    sub-windows and merges them. The per-window limit protects a single
    ``find_entities_filtered`` call, but four windows can each stay under
    that limit while their merged total exceeds the chunk's entity budget.
    The chunk must then be reported as partial, never as complete.

    The Lua below is the *real* budget block taken from the mod source, and
    it is executed in a Lua runtime against a mocked
    ``find_entities_filtered``, so the contract is proved by behaviour and
    not by a string match.
    """

    def setUp(self):
        self.observer = MOD_MAP.read_text(encoding="utf-8")
        # The historical name of the observed source. The observation moved
        # from the backend into the mod, but the probe helpers still refer to
        # it, so the alias is kept.
        self.tools = self.observer

    # -- source extraction -------------------------------------------------

    def _lua_budget_block(self, content):
        """Return the collection loop from the mod's observer."""
        start = content.index("    for _, group in ipairs(GROUPS) do")
        end = content.index("        for _, entity in ipairs(found) do", start)
        # The extracted slice leaves the group loop open; close it so the
        # block is a complete program.
        return content[start:end] + "    end\n"

    def _lua_constants(self, content):
        """Return the map-chunk limit constants from the observer."""
        names = []
        for name in (
            "MAP_CHUNK_TILES",
            "MAP_CHUNK_ENTITY_LIMIT",
            "MAP_CHUNK_ENTITY_BUDGET",
            "MAP_CHUNK_WINDOW_TILES",
        ):
            match = re.search(r"local " + name + r" = (\d+)", content)
            assert match is not None, (
                f"{name} is missing from the mod observation"
            )
            names.append((name, int(match.group(1))))
        return names

    def _lua_program(self, content):
        """Build a runnable Lua program around the real budget block."""
        constants = "\n".join(
            f"local {name}={value}" for name, value in self._lua_constants(content)
        )
        block = self._lua_budget_block(content)
        preamble = """
local origin_x=0
local origin_y=0
local partial=false
local chunk_complete=true
local window_counts={}
local surface={find_entities_filtered=function(opts)
    local a=opts.area
    local key=(a[1][1])..","..(a[1][2])..":"..(a[2][1]-a[1][1]).."x"..(a[2][2]-a[1][2])
    local held=window_counts[key] or 0
    local limit=opts.limit or held
    local count=held
    if count>limit then count=limit end
    local rows={}
    for i=1,count do rows[i]={name="entity-"..key.."-"..i} end
    return rows
end}
local player={force={name="player"}}
local GROUPS={{kind="resource",types={{"resource"}}}}
"""
        epilogue = "\nreturn {partial=partial,chunk_complete=chunk_complete}\n"
        return constants + preamble + block + epilogue

    def _run_lua(self, content, window_counts):
        """Run the real budget block in Lua and return partial/chunk_complete."""
        try:
            import lupa
        except ImportError:  # pragma: no cover - depends on the environment
            self.skipTest("lupa is not installed; the Lua contract cannot run")
        program = self._lua_program(content).replace(
            "local window_counts={}",
            "local window_counts=" + _lua_table(window_counts),
        )
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        result = lua.execute(program)
        # lupa returns an untyped object at runtime; keep the Lua table access
        # explicit for static type checkers without changing behavior.
        result = cast(
            dict[str, Any],
            result if isinstance(result, dict) else dict(result),  # type: ignore[arg-type]
        )
        return {
            "partial": bool(result["partial"]),
            "chunk_complete": bool(result["chunk_complete"]),
        }

    # -- the contract ------------------------------------------------------

    def test_the_chunk_budget_is_a_separate_documented_bound(self):
        """The chunk budget and the per-window limit are distinct bounds."""
        constants = dict(self._lua_constants(self.observer))
        self.assertEqual(constants["MAP_CHUNK_TILES"], 64)
        self.assertEqual(constants["MAP_CHUNK_WINDOW_TILES"], 32)
        self.assertEqual(constants["MAP_CHUNK_ENTITY_LIMIT"], 512)
        self.assertEqual(constants["MAP_CHUNK_ENTITY_BUDGET"], 2048)
        # The budget must bound the merged count, because the chunk-level
        # decision uses the merged count.
        self.assertIn("MAP_CHUNK_ENTITY_BUDGET", self.observer)

    def test_a_chunk_whose_merged_count_exceeds_the_budget_is_partial(self):
        """Four under-limit sub-windows that overflow the budget are partial.

        Each of the four 32x32 sub-windows holds 600 entities, so every
        sub-window is under the per-window limit of 512, but the merged
        chunk count of 2400 exceeds the chunk budget of 2048. The chunk must
        be reported as partial and never as complete.
        """
        window_counts = {
            "0,0:32x32": 600,
            "32,0:32x32": 600,
            "0,32:32x32": 600,
            "32,32:32x32": 600,
        }
        result = self._run_lua(self.observer, window_counts)
        self.assertTrue(
            result["partial"],
            "a chunk whose merged entity count exceeds the budget was "
            "not reported as partial",
        )
        self.assertFalse(
            result["chunk_complete"],
            "a chunk whose merged entity count exceeds the budget was "
            "reported as complete",
        )

    def test_a_chunk_under_the_budget_stays_complete(self):
        """A chunk whose merged count stays under the budget is complete."""
        window_counts = {
            "0,0:32x32": 100,
            "32,0:32x32": 100,
            "0,32:32x32": 100,
            "32,32:32x32": 100,
        }
        result = self._run_lua(self.observer, window_counts)
        self.assertFalse(result["partial"])
        self.assertTrue(result["chunk_complete"])

    def test_a_single_dense_sub_window_is_still_partial(self):
        """One over-limit sub-window keeps marking the chunk partial."""
        window_counts = {
            "0,0:32x32": 3000,
            "32,0:32x32": 0,
            "0,32:32x32": 0,
            "32,32:32x32": 0,
        }
        result = self._run_lua(self.observer, window_counts)
        self.assertTrue(result["partial"])
        self.assertFalse(result["chunk_complete"])


def _lua_table(mapping):
    """Render a Python mapping as a Lua table constructor."""
    parts = [f'["{key}"]={value}' for key, value in mapping.items()]
    return "{" + ",".join(parts) + "}"


if __name__ == "__main__":
    unittest.main()
