import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"
PATCH = ROOT / "backend-safety" / "backend-safety.patch"


class NatureObservationContractTests(unittest.TestCase):
    """The read-only observer must report what the map layer needs, and only that."""

    def setUp(self):
        self.tools = (ROOT / "backend-safety" / "AutoEngineerTools.cs").read_text(
            encoding="utf-8"
        )
        self.patch = PATCH.read_text(encoding="utf-8")

    def test_the_nature_filter_includes_cliffs(self):
        # Factorio 2.1.23 cliffs have the entity type "cliff"; the previous
        # filter only listed trees and simple entities, so no cliff was ever
        # observed.
        for content in (self.tools, self.patch):
            self.assertIn('{kind="nature",types={"tree","simple-entity","cliff"}', content)

    def test_the_observer_reports_the_prototype_chart_colour(self):
        for content in (self.tools, self.patch):
            self.assertIn("friendly_map_color", content)
            self.assertIn("enemy_map_color", content)
            self.assertIn("map_color", content)
            self.assertIn("record.map_color=color", content)

    def test_the_chart_colour_prefers_the_force_specific_colour(self):
        # The 2.1.23 runtime API documents map_color as the colour used "if a
        # friendly or enemy color isn't defined", so the force-specific colour
        # is the one the game charts with.
        for content in (self.tools, self.patch):
            self.assertIn('{"friendly_map_color","enemy_map_color","map_color"}', content)

    def test_the_observer_reports_the_entity_and_prototype_type(self):
        for content in (self.tools, self.patch):
            self.assertIn("record.entity_type=e.type", content)
            self.assertIn("record.prototype_type=ptype", content)

    def test_the_observer_reports_the_observed_direction(self):
        for content in (self.tools, self.patch):
            self.assertIn("record.direction=dir", content)

    def test_the_nature_observation_payload_stays_bounded(self):
        # Nature collection is partitioned by bounded chunks.  The old single
        # 512-entity window allowed one dense forest to exhaust the visible
        # budget before less dense areas were visited.
        for content in (self.tools, self.patch):
            self.assertIn("MAP_CHUNK_TILES=64", content)
            self.assertIn("MAP_CHUNK_ENTITY_LIMIT=2048", content)
            self.assertIn("mapChunkX", content)
            self.assertIn("mapChunkY", content)
            self.assertIn("map_chunk", content)
            self.assertIn("partial=partial", content)
            self.assertIn("return {r=r,g=g,b=b}", content)

    def test_the_observer_checks_visibility_after_chunk_collection(self):
        # find_entities_filtered applies its limit before Lua receives the
        # rows, so a chunk must be explicit and its result marked partial
        # rather than silently presenting a dense forest as complete.
        for content in (self.tools, self.patch):
            self.assertIn("chunk_complete", content)
            self.assertIn("#found>g.limit", content)

    def test_the_nature_observation_adds_no_gameplay_command(self):
        # The observer stays read-only: no charting, no world mutation.
        for content in (self.tools, self.patch):
            self.assertNotIn("surface.create_entity", content)
            self.assertNotIn("surface.chart(", content)
            self.assertNotIn("player.teleport", content)
            self.assertNotIn("game.command", content)

    def test_the_restricted_tool_boundary_is_unchanged(self):
        # The Allowed dictionary must still list exactly the 12 restricted
        # tools. Count the dictionary entries, not every bracket in the file.
        start = self.tools.index("internal static readonly Dictionary<string, string[]> Allowed")
        end = self.tools.index("};", start)
        allowed = self.tools[start:end]
        names = re.findall(r'\["([a-z_]+)"\]\s*=', allowed)
        self.assertEqual(len(names), 12)
        self.assertEqual(len(set(names)), 12)
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
        source = ADAPTER.read_text(encoding="utf-8")
        tools = (ROOT / "backend-safety" / "AutoEngineerTools.cs").read_text(encoding="utf-8")
        patch = PATCH.read_text(encoding="utf-8")
        for content in (source, patch):
            self.assertIn("get_item_production_statistics", content)
            self.assertIn("get_fluid_production_statistics", content)
            self.assertIn("precision_index=defines.flow_precision_index.ten_minutes", content)
            self.assertIn("maximum_production", content)
            self.assertIn("joules_per_tick", content)
            self.assertIn("candidate_bucket_count", content)
        self.assertIn("telemetry=telemetry", tools)
        self.assertIn("+                telemetry=telemetry,", patch)

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


if __name__ == "__main__":
    unittest.main()
