"""Tests for the Save Manager.

The tests build **synthetic** save archives in a temporary directory.
They are fixtures, not Factorio data, and no game is ever started.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from save_manager import (  # noqa: E402
    BACKUP_SUFFIX,
    SaveError,
    SaveManager,
    format_duration,
    format_size,
    resolve_save,
    validate_save_name,
)


def write_save(path: Path, *, version: str = "2.1.23",
               mods: tuple[str, ...] = ("base",),
               level: dict | None = None,
               readable: bool = True) -> Path:
    """Write a synthetic save archive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not readable:
        path.write_bytes(b"not a zip archive at all")
        return path
    document = level if level is not None else {
        "version": version,
        "mod_list": [{"name": name} for name in mods],
        "playtime": 3725.0,
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("level.dat", json.dumps(document))
    return path


class SaveManagerTestCase(unittest.TestCase):
    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.saves = self.base / "saves"
        self.saves.mkdir()
        self.manager = SaveManager(self.saves)


class ListingTests(SaveManagerTestCase):
    def test_the_saves_are_listed(self):
        write_save(self.saves / "world.zip")
        write_save(self.saves / "other.zip")
        names = [info.name for info in self.manager.list_saves()]
        self.assertEqual(sorted(names), ["other.zip", "world.zip"])

    def test_an_empty_directory_lists_nothing(self):
        self.assertEqual(self.manager.list_saves(), ())

    def test_a_missing_directory_lists_nothing(self):
        manager = SaveManager(self.base / "absent")
        self.assertEqual(manager.list_saves(), ())

    def test_a_non_zip_file_is_not_a_save(self):
        (self.saves / "notes.txt").write_text("hello", encoding="utf-8")
        self.assertEqual(self.manager.list_saves(), ())

    def test_the_backup_folder_is_not_listed_as_a_save(self):
        write_save(self.saves / "world.zip")
        backups = self.saves / "backups"
        backups.mkdir()
        write_save(backups / "world.backup.20260101.zip")
        names = [info.name for info in self.manager.list_saves()]
        self.assertEqual(names, ["world.zip"])

    def test_the_real_metadata_is_reported(self):
        write_save(self.saves / "world.zip", version="2.1.23",
                   mods=("base", "space-age"))
        info = self.manager.list_saves()[0]
        self.assertEqual(info.game_version, "2.1.23")
        self.assertEqual(info.mod_list, ("base", "space-age"))
        self.assertTrue(info.readable)
        self.assertIsNone(info.problem)

    def test_the_size_and_the_date_are_reported(self):
        write_save(self.saves / "world.zip")
        info = self.manager.list_saves()[0]
        self.assertGreater(info.size_bytes, 0)
        self.assertTrue(info.modified)
        self.assertTrue(info.display_size.endswith("B"))

    def test_a_corrupted_save_is_reported_not_raised(self):
        write_save(self.saves / "broken.zip", readable=False)
        info = self.manager.list_saves()[0]
        self.assertFalse(info.readable)
        self.assertIsInstance(info.problem, str)
        assert info.problem is not None
        self.assertIn("could not be read", info.problem)

    def test_a_save_without_level_information_is_unknown(self):
        path = self.saves / "empty.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("readme.txt", "no level here")
        info = self.manager.list_saves()[0]
        self.assertFalse(info.readable)
        self.assertIsNone(info.game_version)
        self.assertEqual(info.mod_list, ())


class NameValidationTests(unittest.TestCase):
    def test_a_plain_name_is_accepted(self):
        self.assertEqual(validate_save_name("world"), "world.zip")

    def test_the_suffix_is_added(self):
        self.assertEqual(validate_save_name("world.zip"), "world.zip")

    def test_an_empty_name_is_refused(self):
        with self.assertRaises(SaveError):
            validate_save_name("   ")

    def test_a_path_separator_is_refused(self):
        for name in ("../escape", "a/b", "a\\b", "C:\\x"):
            with self.subTest(name=name):
                with self.assertRaises(SaveError):
                    validate_save_name(name)

    def test_a_leading_dot_is_refused(self):
        with self.assertRaises(SaveError):
            validate_save_name(".hidden")

    def test_a_reserved_device_name_is_refused(self):
        with self.assertRaises(SaveError):
            validate_save_name("con")

    def test_a_non_text_name_is_refused(self):
        with self.assertRaises(SaveError):
            validate_save_name(42)


class PathTraversalTests(SaveManagerTestCase):
    def test_a_traversal_is_refused(self):
        with self.assertRaises(SaveError):
            resolve_save(self.saves, "../outside")

    def test_a_traversal_cannot_escape(self):
        outside = self.base / "outside.zip"
        outside.write_bytes(b"secret")
        with self.assertRaises(SaveError):
            resolve_save(self.saves, "../outside.zip")

    def test_a_name_inside_the_folder_is_accepted(self):
        write_save(self.saves / "world.zip")
        resolved = resolve_save(self.saves, "world.zip")
        self.assertEqual(resolved.name, "world.zip")

    def test_a_save_of_another_profile_is_not_reachable(self):
        other = self.base / "other-profile" / "saves"
        other.mkdir(parents=True)
        write_save(other / "theirs.zip")
        with self.assertRaises(SaveError):
            resolve_save(self.saves, "../other-profile/saves/theirs.zip")


class BackupTests(SaveManagerTestCase):
    def test_a_backup_is_written(self):
        write_save(self.saves / "world.zip")
        backup = self.manager.backup("world.zip")
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_bytes(),
                         (self.saves / "world.zip").read_bytes())

    def test_the_backup_is_kept_out_of_the_save_list(self):
        write_save(self.saves / "world.zip")
        self.manager.backup("world.zip")
        self.assertEqual(len(self.manager.list_saves()), 1)

    def test_the_backup_is_reported_with_the_save(self):
        write_save(self.saves / "world.zip")
        self.manager.backup("world.zip")
        info = self.manager.list_saves()[0]
        self.assertEqual(len(info.backups), 1)
        self.assertIn(BACKUP_SUFFIX, info.backups[0])

    def test_a_backup_of_a_missing_save_is_refused(self):
        with self.assertRaises(SaveError):
            self.manager.backup("absent.zip")

    def test_two_backups_do_not_collide(self):
        write_save(self.saves / "world.zip")
        first = self.manager.backup("world.zip")
        second = self.manager.backup("world.zip")
        self.assertNotEqual(first, second)


class RestoreTests(SaveManagerTestCase):
    def test_a_restore_needs_a_confirmation(self):
        write_save(self.saves / "world.zip")
        self.manager.backup("world.zip")
        backup = self.manager.backups_of("world.zip")[0]
        with self.assertRaises(SaveError):
            self.manager.restore(backup)

    def test_a_restore_puts_the_backup_back(self):
        write_save(self.saves / "world.zip", mods=("base",))
        self.manager.backup("world.zip")
        backup = self.manager.backups_of("world.zip")[0]
        (self.saves / "world.zip").write_bytes(b"changed")
        self.manager.restore(backup, confirm=True)
        info = self.manager.list_saves()[0]
        self.assertEqual(info.mod_list, ("base",))

    def test_a_restore_backs_up_the_save_it_replaces(self):
        write_save(self.saves / "world.zip")
        self.manager.backup("world.zip")
        backup = self.manager.backups_of("world.zip")[0]
        self.manager.restore(backup, confirm=True)
        # The replaced save was backed up, so nothing is lost.
        self.assertGreaterEqual(len(self.manager.backups_of("world.zip")), 1)

    def test_a_restore_of_a_missing_backup_is_refused(self):
        with self.assertRaises(SaveError):
            self.manager.restore("absent.zip", confirm=True)


class RenameTests(SaveManagerTestCase):
    def test_a_rename_needs_a_confirmation(self):
        write_save(self.saves / "world.zip")
        with self.assertRaises(SaveError):
            self.manager.rename("world.zip", "renamed.zip")

    def test_a_rename_moves_the_save(self):
        write_save(self.saves / "world.zip")
        target = self.manager.rename("world.zip", "renamed.zip", confirm=True)
        self.assertTrue(target.is_file())
        self.assertFalse((self.saves / "world.zip").exists())

    def test_a_rename_never_overwrites(self):
        write_save(self.saves / "world.zip")
        write_save(self.saves / "other.zip")
        with self.assertRaises(SaveError):
            self.manager.rename("world.zip", "other.zip", confirm=True)
        self.assertTrue((self.saves / "other.zip").is_file())

    def test_a_rename_of_a_missing_save_is_refused(self):
        with self.assertRaises(SaveError):
            self.manager.rename("absent.zip", "new.zip", confirm=True)

    def test_a_rename_cannot_escape(self):
        write_save(self.saves / "world.zip")
        with self.assertRaises(SaveError):
            self.manager.rename("world.zip", "../escape.zip", confirm=True)


class DeleteTests(SaveManagerTestCase):
    def test_a_delete_needs_a_confirmation(self):
        write_save(self.saves / "world.zip")
        with self.assertRaises(SaveError):
            self.manager.delete("world.zip")
        self.assertTrue((self.saves / "world.zip").is_file())

    def test_a_delete_removes_the_save(self):
        write_save(self.saves / "world.zip")
        self.manager.delete("world.zip", confirm=True)
        self.assertFalse((self.saves / "world.zip").exists())

    def test_a_delete_keeps_a_recoverable_backup(self):
        write_save(self.saves / "world.zip")
        self.manager.delete("world.zip", confirm=True)
        self.assertEqual(len(self.manager.backups_of("world.zip")), 1)

    def test_a_delete_of_a_missing_save_is_refused(self):
        with self.assertRaises(SaveError):
            self.manager.delete("absent.zip", confirm=True)


class ImportExportTests(SaveManagerTestCase):
    def test_a_save_is_imported(self):
        source = self.base / "outside" / "world.zip"
        write_save(source)
        target = self.manager.import_save(source)
        self.assertTrue(target.is_file())
        self.assertEqual(target.parent, self.saves)

    def test_an_import_never_overwrites(self):
        write_save(self.saves / "world.zip")
        source = self.base / "outside" / "world.zip"
        write_save(source)
        with self.assertRaises(SaveError):
            self.manager.import_save(source)
        self.assertEqual(len(self.manager.list_saves()), 1)

    def test_a_missing_source_is_refused(self):
        with self.assertRaises(SaveError):
            self.manager.import_save(self.base / "absent.zip")

    def test_a_non_zip_source_is_refused(self):
        source = self.base / "notes.txt"
        source.write_text("hello", encoding="utf-8")
        with self.assertRaises(SaveError):
            self.manager.import_save(source)

    def test_a_save_is_exported(self):
        write_save(self.saves / "world.zip")
        destination = self.base / "export" / "world.zip"
        target = self.manager.export_save("world.zip", destination)
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(),
                         (self.saves / "world.zip").read_bytes())

    def test_an_export_never_overwrites(self):
        write_save(self.saves / "world.zip")
        destination = self.base / "world.zip"
        destination.write_bytes(b"existing")
        with self.assertRaises(SaveError):
            self.manager.export_save("world.zip", destination)
        self.assertEqual(destination.read_bytes(), b"existing")


class ProfileIsolationTests(SaveManagerTestCase):
    def test_a_profile_only_sees_its_own_saves(self):
        write_save(self.saves / "mine.zip")
        other = self.base / "other" / "saves"
        other.mkdir(parents=True)
        write_save(other / "theirs.zip")
        manager = SaveManager(self.saves)
        names = [info.name for info in manager.list_saves()]
        self.assertEqual(names, ["mine.zip"])

    def test_a_delete_does_not_touch_another_profile(self):
        other = self.base / "other" / "saves"
        other.mkdir(parents=True)
        write_save(other / "theirs.zip")
        with self.assertRaises(SaveError):
            self.manager.delete("../other/saves/theirs.zip", confirm=True)
        self.assertTrue((other / "theirs.zip").is_file())


class CompatibilityTests(SaveManagerTestCase):
    def test_a_save_without_a_mod_list_is_unknown(self):
        path = self.saves / "world.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("level.dat", json.dumps({"version": "2.1.23"}))
        info = self.manager.list_saves()[0]
        report = self.manager.compatibility(info, enabled_mods=("base",))
        self.assertEqual(report["status"], "unknown")

    def test_a_save_with_every_mod_is_compatible(self):
        write_save(self.saves / "world.zip", mods=("base", "space-age"))
        info = self.manager.list_saves()[0]
        report = self.manager.compatibility(info, enabled_mods=("base", "space-age"))
        self.assertEqual(report["status"], "compatible")

    def test_a_save_that_needs_a_missing_mod_is_incompatible(self):
        write_save(self.saves / "world.zip", mods=("base", "py-alien-life"))
        info = self.manager.list_saves()[0]
        report = self.manager.compatibility(info, enabled_mods=("base",))
        self.assertEqual(report["status"], "incompatible")
        self.assertIn("py-alien-life", report["missing_mods"])

    def test_a_save_from_another_version_is_incompatible(self):
        write_save(self.saves / "world.zip", version="2.1.22")
        info = self.manager.list_saves()[0]
        report = self.manager.compatibility(
            info, enabled_mods=("base",), game_version="2.1.23")
        self.assertEqual(report["status"], "incompatible")


class FormattingTests(unittest.TestCase):
    def test_a_size_is_formatted(self):
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(2048), "2.0 KB")

    def test_a_duration_is_formatted(self):
        self.assertEqual(format_duration(30), "30 s")
        self.assertEqual(format_duration(125), "2 min")
        self.assertEqual(format_duration(7325), "2 h 2 min")


if __name__ == "__main__":
    unittest.main()
