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


if __name__ == "__main__":
    unittest.main()
