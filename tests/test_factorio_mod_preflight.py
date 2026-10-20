"""Offline preflight for Factorio mod source folders. No game launch or mod edits."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODS = ROOT / "factorio-mod"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


class FactorioModPreflight(unittest.TestCase):
    def test_mod_folders_are_well_formed(self):
        folders = sorted(p for p in MODS.iterdir() if p.is_dir() and (p / "info.json").is_file())
        self.assertTrue(folders, "No unpacked Factorio mod folders found")
        for folder in folders:
            with self.subTest(mod=folder.name):
                meta = json.loads((folder / "info.json").read_text(encoding="utf-8-sig"))
                for key in ("name", "version", "title", "factorio_version"):
                    self.assertIsInstance(meta.get(key), str, f"{key} missing in {folder}")
                    self.assertTrue(meta[key].strip())
                self.assertRegex(meta["name"], NAME)
                self.assertRegex(meta["version"], SEMVER)
                self.assertRegex(meta["factorio_version"], r"^\d+\.\d+$")
                self.assertEqual(folder.name, meta["name"] + "_" + meta["version"])
                dependencies = meta.get("dependencies", [])
                self.assertIsInstance(dependencies, list)
                self.assertTrue(all(isinstance(d, str) and d.strip() for d in dependencies))
                lua = list(folder.rglob("*.lua"))
                self.assertTrue(lua, "Mod contains no Lua files")
                self.assertTrue(any((folder / n).exists() for n in ("control.lua", "data.lua", "settings.lua")),
                                "No Factorio mod entry point")
                for file in lua:
                    self.assertLess(file.stat().st_size, 2 * 1024 * 1024, f"Oversized Lua module: {file}")
                    content = file.read_text(encoding="utf-8-sig")
                    self.assertNotIn("\x00", content, f"NUL byte in {file}")
                    self.assertNotIn("\r\r\n", content, f"Malformed newlines in {file}")
                for file in folder.rglob("*"):
                    if file.is_file():
                        self.assertNotIn(file.suffix.lower(), (".exe", ".dll", ".bat", ".cmd", ".ps1"),
                                         f"Unexpected executable in mod package: {file}")


if __name__ == "__main__":
    unittest.main()
