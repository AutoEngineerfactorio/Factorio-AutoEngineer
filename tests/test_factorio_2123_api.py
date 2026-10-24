"""Factorio 2.1.23 version and Lua API compatibility for the input guard.

Installed API checks are skipped on systems without this isolated Factorio build.
This does not claim all R05 telemetry acceptance has been rerun on 2.1.23.

The offline API archive under ``.local/factorio-api-offline/2.1.23/files`` is the
authoritative local reference for the supported target. It is copied verbatim from
the verified 2.1.23 installation, so its machine-readable definitions must agree
with the installed ``doc-html`` whenever both are present.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")
INSTALLED = EXE.parents[2] / "doc-html"
API = INSTALLED / "runtime-api.json"
PROTOTYPE_API = INSTALLED / "prototype-api.json"
OFFLINE_API = ROOT / ".local" / "factorio-api-offline" / "2.1.23" / "files"
OFFLINE_RUNTIME = OFFLINE_API / "runtime-api.json"
OFFLINE_PROTOTYPE = OFFLINE_API / "prototype-api.json"
OFFLINE_INDEX = OFFLINE_API / "index.html"
OFFLINE_LICENSE = OFFLINE_API / "license.html"


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


class Factorio2123OfflineAPIArchive(unittest.TestCase):
    """The supported offline reference must be the exact 2.1.23 API.

    These assertions fail closed: if the archive is missing, truncated, or
    declares another version, the test fails rather than silently skipping, so a
    stale 2.1.22 or 2.0.77 archive can never be mistaken for the current API.
    """

    def test_offline_archive_declares_2_1_23(self):
        for path, stage in (
            (OFFLINE_RUNTIME, "runtime"),
            (OFFLINE_PROTOTYPE, "prototype"),
        ):
            with self.subTest(stage=stage):
                self.assertTrue(path.is_file(), f"missing offline {stage} API: {path}")
                spec = json.loads(path.read_text(encoding="utf8"))
                self.assertEqual(spec["application"], "factorio")
                self.assertEqual(spec["application_version"], "2.1.23")
                self.assertEqual(spec["stage"], stage)

    def test_offline_archive_contains_classes_events_and_prototypes(self):
        runtime = json.loads(OFFLINE_RUNTIME.read_text(encoding="utf8"))
        self.assertGreater(len(runtime["classes"]), 100)
        self.assertGreater(len(runtime["events"]), 100)
        prototype = json.loads(OFFLINE_PROTOTYPE.read_text(encoding="utf8"))
        self.assertGreater(len(prototype["prototypes"]), 100)
        self.assertGreater(len(prototype["types"]), 100)

    def test_offline_archive_html_declares_version(self):
        self.assertTrue(OFFLINE_INDEX.is_file())
        index = OFFLINE_INDEX.read_text(encoding="utf-8")
        self.assertIn("2.1.23", index)

    def test_offline_archive_preserves_upstream_license(self):
        self.assertTrue(OFFLINE_LICENSE.is_file())
        license_text = OFFLINE_LICENSE.read_text(encoding="utf-8")
        self.assertIn("Wube", license_text)
        self.assertIn("Copyright", license_text)

    def test_offline_archive_matches_installed_api_when_both_present(self):
        if not API.is_file():
            self.skipTest("installed 2.1.23 API unavailable; archive alone verified")
        for offline, installed in (
            (OFFLINE_RUNTIME, INSTALLED / "runtime-api.json"),
            (OFFLINE_PROTOTYPE, PROTOTYPE_API),
        ):
            with self.subTest(file=offline.name):
                self.assertEqual(
                    offline.read_bytes(),
                    installed.read_bytes(),
                    "offline archive drifted from the installed 2.1.23 API",
                )


if __name__ == "__main__":
    unittest.main()
