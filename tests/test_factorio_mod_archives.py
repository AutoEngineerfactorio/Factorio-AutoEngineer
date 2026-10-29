"""Regression tests for archived and built-in Factorio profile mods."""
import json
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from factorio_profiles import ProfileManager, read_mod_list  # noqa: E402


class ModArchiveTests(unittest.TestCase):
    def test_archived_and_builtin_mods_in_separate_profile_mod_folder(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            (game / "bin" / "x64").mkdir(parents=True)
            (game / "bin" / "x64" / "factorio.exe").write_bytes(b"MZ test")
            builtin = game / "data" / "base"
            builtin.mkdir(parents=True)
            (builtin / "info.json").write_text(
                json.dumps({"name": "base", "version": "2.1.23"}))
            mods = root / "external-mods"
            mods.mkdir()
            (mods / "mod-list.json").write_text(json.dumps({"mods": [
                {"name": "base", "enabled": True},
                {"name": "archived", "enabled": True},
            ]}))
            with zipfile.ZipFile(mods / "archived_1.0.0.zip", "w") as archive:
                archive.writestr("archived_1.0.0/info.json", json.dumps({
                    "name": "archived", "version": "1.0.0",
                    "dependencies": ["base >= 2.1.23", "? other >= 1.0"],
                }))
            catalog = read_mod_list(mods, game)
            self.assertFalse(any(not mod.installed for mod in catalog))
            manager = ProfileManager(root / "profiles")
            profile = manager.create("mod archive test", game, mods_directory=mods)
            self.assertFalse(any("mod" in issue.lower() for issue in manager.validate(profile.identifier)))
            self.assertEqual(len(profile.enabled_mods), 2)

    def test_conflict_dependency_is_detected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            (game / "bin" / "x64").mkdir(parents=True)
            (game / "bin" / "x64" / "factorio.exe").write_bytes(b"MZ test")
            mods = game / "mods"
            mods.mkdir()
            (mods / "mod-list.json").write_text(json.dumps({"mods": [
                {"name": "first", "enabled": True},
                {"name": "second", "enabled": True},
            ]}))
            for name, dependencies in [("first", ["! second"]), ("second", [])]:
                folder = mods / name
                folder.mkdir()
                (folder / "info.json").write_text(json.dumps({
                    "name": name, "version": "1.0.0",
                    "dependencies": dependencies,
                }))
            manager = ProfileManager(root / "profiles")
            profile = manager.create("conflict test", game)
            self.assertIn("first conflicts with second", manager.validate(profile.identifier))


if __name__ == "__main__":
    unittest.main()
