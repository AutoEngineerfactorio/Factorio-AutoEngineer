"""Factorio 2.1.23 version and Lua API compatibility for the input guard.

Installed API checks are skipped on systems without this isolated Factorio build.
This does not claim all R05 telemetry acceptance has been rerun on 2.1.23.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")
API = EXE.parents[2] / "doc-html" / "runtime-api.json"


class Factorio2123LuaAPI(unittest.TestCase):
    def test_active_mod_release_and_lease_reset_on_respawn(self):
        meta = json.loads((MOD / "info.json").read_text(encoding="utf8"))
        self.assertEqual(meta["version"], "2.1.23")
        self.assertEqual(meta["factorio_version"], "2.1")
        self.assertIn("base >= 2.1.23", meta["dependencies"])
        source = (MOD / "control.lua").read_text(encoding="utf8")
        self.assertIn(
            "script.on_event(defines.events.on_player_respawned, takeover)", source
        )
        self.assertIn(
            "script.on_event(defines.events.on_player_controller_changed, takeover)",
            source,
        )
        self.assertNotIn("player_port", source)
        self.assertTrue((MOD / "data.lua").is_file())
        self.assertTrue((MOD / "inputs.lua").is_file())

    @unittest.skipUnless(API.is_file(), "Factorio 2.1.23 installed runtime API unavailable")
    def test_installed_api_event_and_input_contract(self):
        spec = json.loads(API.read_text(encoding="utf8"))
        self.assertEqual(spec["application_version"], "2.1.23")
        respawn = next(
            e for e in spec["events"] if e["name"] == "on_player_respawned"
        )
        fields = {p["name"] for p in respawn["data"]}
        self.assertIn("player_index", fields)
        self.assertNotIn("player_port", fields)
        scripts = next(
            c for c in spec["classes"] if c["name"] == "LuaBootstrap"
        )
        self.assertIn("on_event", {m["name"] for m in scripts["methods"]})

    @unittest.skipUnless(API.is_file(), "Factorio 2.1.23 installed runtime API unavailable")
    def test_new_213_api_additions_not_mistaken_for_required_input_fields(self):
        spec = json.loads(API.read_text(encoding="utf8"))
        flags = next(
            c for c in spec["concepts"] if c["name"] == "ItemPrototypeFlag"
        )
        self.assertIn(
            "disable-logistic-overlay",
            {value["value"] for value in flags["type"]["options"]},
        )
        game = next(c for c in spec["classes"] if c["name"] == "LuaGameScript")
        capture = next(m for m in game["methods"] if m["name"] == "take_screenshot")
        self.assertIn(
            "hide_health_bars",
            {p["name"] for p in capture["parameters"]},
        )


if __name__ == "__main__":
    unittest.main()
