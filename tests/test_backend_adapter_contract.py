import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"
PATCH = ROOT / "backend-safety" / "backend-safety.patch"


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

    def test_version_gated_20_historical_power_never_fabricates_21_metrics(self):
        source = ADAPTER.read_text(encoding="utf-8")
        patch = PATCH.read_text(encoding="utf-8")
        for body in (source, patch):
            self.assertIn('script.active_mods["base"] or ""', body)
            self.assertIn('legacy_20 = base_version:match("^2%.0%.") ~= nil', body)
            self.assertIn("pole.electric_network_statistics", body)
            self.assertIn('source="legacy_statistics"', body)
            self.assertIn("history_available=has_history", body)
            self.assertIn("observed_input=observed_input", body)
            self.assertIn("observed_output=observed_output", body)
            self.assertIn("pole.electric_network", body)
            self.assertIn("parent.flow_last_tick", body)
            self.assertIn("partial=partial or legacy_20", body)

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
