"""Tests for the universal Factorio profile manager.

The installations and mod sets used here are **fixtures**: they are built
in a temporary directory and they are not vanilla or Pyanodons data. They
prove that the manager works from the installation's own ``mod-list.json``
and ``info.json`` files, and that it never depends on the name of a mod.

No Factorio process is started and no real save is touched.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from factorio_profiles import (  # noqa: E402
    PROFILE_FILE,
    SUPPORTED_GAME_VERSION,
    Profile,
    ProfileError,
    ProfileManager,
    detect_installation,
    discover_installations,
    read_mod_list,
    validate_name,
)


def make_installation(root: Path, *, version: str = "2.1.23",
                      mods: dict[str, str | None] | None = None,
                      enabled: tuple[str, ...] = (),
                      dependencies: dict[str, list[str]] | None = None,
                      with_executable: bool = True) -> Path:
    """Build a fake Factorio installation on disk."""
    executable = root / "bin" / "x64" / "factorio.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    if with_executable:
        executable.write_bytes(b"MZ fake factorio")
    mods_directory = root / "mods"
    mods_directory.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in (mods if mods is not None else {"base": "1.1.1"}):
        folder = mods_directory / f"{name}_1.0.0"
        folder.mkdir(parents=True, exist_ok=True)
        info: dict = {"name": name, "version": "1.0.0", "title": name}
        if dependencies and name in dependencies:
            info["dependencies"] = dependencies[name]
        (folder / "info.json").write_text(
            json.dumps(info), encoding="utf-8")
        entries.append({"name": name, "enabled": name in enabled})
    (mods_directory / "mod-list.json").write_text(
        json.dumps({"mods": entries}), encoding="utf-8")
    return root


class ProfileManagerTestCase(unittest.TestCase):
    """A manager with one fake installation and an empty profile root."""

    def setUp(self) -> None:
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.base = Path(self._temporary.name)
        self.installation = make_installation(
            self.base / "Factorio",
            mods={"base": "1.1.1", "space-age": "2.0.0"},
            enabled=("base", "space-age"))
        self.root = self.base / "profiles"
        self.manager = ProfileManager(self.root)


class InstallationDetectionTests(ProfileManagerTestCase):
    def test_an_installation_without_an_executable_is_refused(self):
        empty = self.base / "Empty"
        empty.mkdir()
        installation = detect_installation(empty)
        problem = installation.problem or ""
        self.assertFalse(installation.usable)
        self.assertIn("No Factorio executable", problem)

    def test_a_missing_directory_is_refused(self):
        installation = detect_installation(self.base / "Nope")
        problem = installation.problem or ""
        self.assertFalse(installation.usable)
        self.assertIn("does not exist", problem)

    def test_an_unknown_version_is_reported_as_unknown(self):
        installation = detect_installation(self.installation)
        problem = installation.version_problem or ""
        # The fixture executable carries no Windows version resource, so
        # the version must stay unknown instead of being invented.
        self.assertIsNone(installation.game_version)
        self.assertTrue(installation.usable)
        self.assertFalse(installation.valid)
        self.assertIn("could not be read", problem)

    def test_an_installation_without_an_executable_is_not_usable(self):
        empty = self.base / "Empty2"
        empty.mkdir()
        installation = detect_installation(empty)
        self.assertFalse(installation.usable)
        self.assertFalse(installation.valid)

    def test_the_version_is_never_taken_from_the_directory_name(self):
        stale = make_installation(self.base / "Factorio_2.1.22")
        installation = detect_installation(stale)
        self.assertNotEqual(installation.game_version, "2.1.22")

    def test_discovery_includes_a_manual_root(self):
        found = discover_installations((self.installation,))
        roots = {str(item.root) for item in found}
        self.assertIn(str(self.installation.resolve()), roots)

    def test_discovery_does_not_duplicate_the_same_root(self):
        found = discover_installations((self.installation,))
        roots = [str(item.root) for item in found]
        self.assertEqual(len(roots), len(set(roots)))


class ModReadingTests(ProfileManagerTestCase):
    def test_the_mod_list_is_read_from_the_installation(self):
        mods = read_mod_list(self.installation / "mods")
        names = {mod.name for mod in mods}
        self.assertIn("base", names)
        self.assertIn("space-age", names)

    def test_an_enabled_mod_that_is_not_installed_is_reported(self):
        mods_directory = self.installation / "mods"
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "ghost", "enabled": True}]}),
            encoding="utf-8")
        mods = read_mod_list(mods_directory)
        ghost = next(mod for mod in mods if mod.name == "ghost")
        self.assertTrue(ghost.enabled)
        self.assertFalse(ghost.installed)

    def test_the_mod_version_comes_from_the_mod_info(self):
        mods = read_mod_list(self.installation / "mods")
        base = next(mod for mod in mods if mod.name == "base")
        self.assertEqual(base.version, "1.0.0")
        self.assertTrue(base.installed)

    def test_dependencies_are_read_from_the_mod_info(self):
        mods_directory = self.installation / "mods"
        folder = mods_directory / "dependent_1.0.0"
        folder.mkdir()
        (folder / "info.json").write_text(
            json.dumps({"name": "dependent", "version": "1.0.0",
                        "dependencies": ["base"]}), encoding="utf-8")
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "dependent", "enabled": True}]}),
            encoding="utf-8")
        mods = read_mod_list(mods_directory)
        dependent = next(mod for mod in mods if mod.name == "dependent")
        self.assertEqual(dependent.dependencies, ("base",))


class NameValidationTests(unittest.TestCase):
    def test_an_empty_name_is_refused(self):
        with self.assertRaises(ProfileError):
            validate_name("  ")

    def test_a_name_with_a_path_separator_is_refused(self):
        with self.assertRaises(ProfileError):
            validate_name("../escape")

    def test_a_name_that_starts_with_a_dot_is_refused(self):
        with self.assertRaises(ProfileError):
            validate_name(".hidden")

    def test_an_ordinary_name_is_accepted(self):
        self.assertEqual(validate_name("  My Modpack  "), "My Modpack")


class ProfileCreationTests(ProfileManagerTestCase):
    def test_a_profile_is_created_with_its_own_directories(self):
        profile = self.manager.create("Test pack", self.installation)
        self.assertTrue((profile.root / PROFILE_FILE_NAME).is_file())
        for child in ("saves", "config", "cache"):
            self.assertTrue((profile.root / child).is_dir())

    def test_creating_a_profile_does_not_write_into_the_installation(self):
        before = sorted(
            str(item) for item in self.installation.rglob("*"))
        self.manager.create("Test pack", self.installation)
        after = sorted(
            str(item) for item in self.installation.rglob("*"))
        self.assertEqual(before, after)

    def test_a_profile_for_a_missing_installation_is_refused(self):
        with self.assertRaises(ProfileError):
            self.manager.create("Bad", self.base / "Nope")

    def test_two_profiles_get_distinct_identifiers(self):
        first = self.manager.create("Same", self.installation)
        second = self.manager.create("Same", self.installation)
        self.assertNotEqual(first.identifier, second.identifier)
        self.assertEqual(len(self.manager.identifiers()), 2)

    def test_the_profile_records_the_observed_mods(self):
        profile = self.manager.create("Test pack", self.installation)
        names = {mod.name for mod in profile.mods}
        self.assertIn("base", names)
        self.assertIn("space-age", names)


class ProfileMutationTests(ProfileManagerTestCase):
    def test_a_profile_can_be_renamed(self):
        profile = self.manager.create("Old name", self.installation)
        renamed = self.manager.rename(profile.identifier, "New name")
        self.assertEqual(renamed.name, "New name")
        self.assertEqual(renamed.identifier, profile.identifier)

    def test_the_notes_can_be_changed(self):
        profile = self.manager.create("Notes", self.installation)
        updated = self.manager.update(profile.identifier, notes="hello")
        self.assertEqual(updated.notes, "hello")

    def test_a_duplicate_owns_its_own_saves(self):
        profile = self.manager.create("Original", self.installation)
        (profile.saves_directory / "world.zip").write_bytes(b"save")
        copy = self.manager.duplicate(profile.identifier, "Copy")
        self.assertNotEqual(copy.saves_directory, profile.saves_directory)
        self.assertTrue((copy.saves_directory / "world.zip").is_file())
        (copy.saves_directory / "world.zip").unlink()
        self.assertTrue((profile.saves_directory / "world.zip").is_file())

    def test_a_duplicate_has_its_own_identifier(self):
        profile = self.manager.create("Original", self.installation)
        copy = self.manager.duplicate(profile.identifier)
        self.assertNotEqual(copy.identifier, profile.identifier)
        self.assertIn("copy", copy.name.lower())

    def test_a_profile_can_be_deleted_with_confirmation(self):
        profile = self.manager.create("Doomed", self.installation)
        with self.assertRaises(ProfileError):
            self.manager.delete(profile.identifier)
        self.manager.delete(profile.identifier, confirm=True)
        self.assertFalse(profile.root.exists())

    def test_deleting_never_touches_the_installation(self):
        profile = self.manager.create("Doomed", self.installation)
        before = sorted(str(item) for item in self.installation.rglob("*"))
        self.manager.delete(profile.identifier, confirm=True)
        after = sorted(str(item) for item in self.installation.rglob("*"))
        self.assertEqual(before, after)


class ProfileImportExportTests(ProfileManagerTestCase):
    def test_a_profile_can_be_exported_and_imported(self):
        profile = self.manager.create("Portable", self.installation)
        exported = self.base / "portable.json"
        self.manager.export_profile(profile.identifier, exported)
        other = ProfileManager(self.base / "other-root")
        imported = other.import_profile(exported)
        self.assertEqual(imported.name, "Portable")
        # The imported profile lives in its own root and owns its own
        # directories, so it is independent of the exported one.
        self.assertNotEqual(imported.root, profile.root)
        self.assertNotEqual(imported.saves_directory, profile.saves_directory)
        self.assertTrue(imported.saves_directory.is_dir())

    def test_importing_never_overwrites_an_existing_profile(self):
        profile = self.manager.create("Portable", self.installation)
        exported = self.base / "portable.json"
        self.manager.export_profile(profile.identifier, exported)
        other = ProfileManager(self.base / "other-root")
        first = other.import_profile(exported)
        second = other.import_profile(exported)
        self.assertNotEqual(first.identifier, second.identifier)
        self.assertEqual(len(other.identifiers()), 2)


class ProfileSelectionTests(ProfileManagerTestCase):
    def test_selecting_a_profile_is_remembered(self):
        profile = self.manager.create("Chosen", self.installation)
        self.manager.select(profile.identifier)
        restored = ProfileManager(self.root).restore_selection()
        self.assertEqual(restored, profile.identifier)

    def test_selecting_does_not_modify_the_profile(self):
        profile = self.manager.create("Chosen", self.installation)
        before = (profile.root / PROFILE_FILE_NAME).read_bytes()
        self.manager.select(profile.identifier)
        after = (profile.root / PROFILE_FILE_NAME).read_bytes()
        self.assertEqual(before, after)

    def test_switching_profiles_leaves_the_first_one_alone(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        (first.saves_directory / "first.zip").write_bytes(b"one")
        self.manager.select(first.identifier)
        self.manager.select(second.identifier)
        self.assertTrue((first.saves_directory / "first.zip").is_file())
        self.assertEqual(self.manager.selected, second.identifier)

    def test_a_selection_of_a_deleted_profile_is_dropped(self):
        profile = self.manager.create("Gone", self.installation)
        self.manager.select(profile.identifier)
        self.manager.delete(profile.identifier, confirm=True)
        self.assertIsNone(ProfileManager(self.root).restore_selection())


class ProfileFingerprintTests(ProfileManagerTestCase):
    def test_the_fingerprint_covers_the_mod_identity(self):
        profile = self.manager.create("Test", self.installation)
        other = self.manager.create("Test 2", self.installation)
        self.assertEqual(profile.fingerprint, other.fingerprint)

    def test_a_mod_change_changes_the_fingerprint(self):
        profile = self.manager.create("Test", self.installation)
        before = profile.fingerprint
        mods_directory = self.installation / "mods"
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "base", "enabled": True},
                                 {"name": "space-age", "enabled": True},
                                 {"name": "extra", "enabled": True}]}),
            encoding="utf-8")
        folder = mods_directory / "extra_1.0.0"
        folder.mkdir()
        (folder / "info.json").write_text(
            json.dumps({"name": "extra", "version": "1.0.0"}), encoding="utf-8")
        updated = self.manager.load(profile.identifier)
        refreshed = Profile(
            identifier=updated.identifier,
            name=updated.name,
            root=updated.root,
            installation_root=updated.installation_root,
            executable=updated.executable,
            mods_directory=updated.mods_directory,
            saves_directory=updated.saves_directory,
            config_directory=updated.config_directory,
            cache_directory=updated.cache_directory,
            game_version=updated.game_version,
            notes=updated.notes,
            mods=read_mod_list(updated.mods_directory),
        )
        self.assertNotEqual(before, refreshed.fingerprint)

    def test_a_missing_mod_is_reported_as_a_problem(self):
        mods_directory = self.installation / "mods"
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "base", "enabled": True},
                                 {"name": "absent-mod", "enabled": True}]}),
            encoding="utf-8")
        profile = self.manager.create("Test", self.installation)
        refreshed = ProfileManager(self.root)
        problems = refreshed.validate(profile.identifier)
        self.assertTrue(any("absent-mod" in problem for problem in problems))

    def test_an_unsatisfied_dependency_is_reported(self):
        mods_directory = self.installation / "mods"
        folder = mods_directory / "needy_1.0.0"
        folder.mkdir()
        (folder / "info.json").write_text(
            json.dumps({"name": "needy", "version": "1.0.0",
                        "dependencies": ["missing-base"]}), encoding="utf-8")
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "needy", "enabled": True}]}),
            encoding="utf-8")
        profile = self.manager.create("Test", self.installation)
        manager = ProfileManager(self.root)
        problems = manager.validate(profile.identifier)
        self.assertTrue(any("missing-base" in problem for problem in problems))


class ProfileIsolationTests(ProfileManagerTestCase):
    """Two profiles of the same installation stay completely separate."""

    def test_two_profiles_never_share_a_save_directory(self):
        first = self.manager.create("Vanilla-like", self.installation)
        second = self.manager.create("Modded-like", self.installation)
        self.assertNotEqual(first.saves_directory, second.saves_directory)
        self.assertNotEqual(first.cache_directory, second.cache_directory)

    def test_switching_does_not_change_the_mod_configuration(self):
        first = self.manager.create("Vanilla-like", self.installation)
        second = self.manager.create("Modded-like", self.installation)
        self.manager.select(first.identifier)
        self.manager.select(second.identifier)
        self.assertEqual(
            self.manager.load(first.identifier).mods_directory,
            self.manager.load(second.identifier).mods_directory)

    def test_deleting_one_profile_leaves_the_other_intact(self):
        first = self.manager.create("One", self.installation)
        second = self.manager.create("Two", self.installation)
        self.manager.delete(first.identifier, confirm=True)
        self.assertEqual(self.manager.identifiers(), [second.identifier])


class ArbitraryModpackTests(ProfileManagerTestCase):
    """A modpack nobody has seen before is handled like any other."""

    def test_an_unknown_modpack_profile_is_usable(self):
        pack = make_installation(
            self.base / "WeirdPack",
            mods={"totally-unknown": "9.9.9", "another-unknown": "0.1.0"},
            enabled=("totally-unknown", "another-unknown"))
        profile = self.manager.create("Weird pack", pack)
        names = {mod.name for mod in profile.mods}
        self.assertEqual(names, {"totally-unknown", "another-unknown"})

    def test_an_unknown_modpack_needs_no_vanilla_assumption(self):
        pack = make_installation(
            self.base / "NoBasePack", mods={"only-mod": "1.0.0"},
            enabled=("only-mod",))
        profile = self.manager.create("No base", pack)
        self.assertEqual([mod.name for mod in profile.mods], ["only-mod"])

    def test_a_modpack_without_a_mod_list_still_profiles(self):
        pack = make_installation(self.base / "EmptyPack", mods={}, enabled=())
        profile = self.manager.create("Empty pack", pack)
        self.assertEqual(profile.mods, ())


class ProfileStatusTests(ProfileManagerTestCase):
    def test_the_status_reports_the_truth(self):
        profile = self.manager.create("Status", self.installation)
        status = self.manager.status(profile.identifier)
        self.assertTrue(status["readable"])
        self.assertEqual(status["supported_version"], SUPPORTED_GAME_VERSION)
        self.assertFalse(status["version_ok"])
        self.assertIn("fingerprint", status)

    def test_the_status_of_an_unknown_profile_is_not_an_exception(self):
        status = self.manager.status("does-not-exist")
        self.assertFalse(status["readable"])
        self.assertTrue(status["problems"])


class ProfileConfigIniTests(ProfileManagerTestCase):
    def test_the_config_points_at_the_profiles_own_write_data(self):
        profile = self.manager.create("Config", self.installation)
        path = self.manager.write_config_ini(profile.identifier)
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn(f"write-data={profile.root}", text)

    def test_the_config_reads_the_installations_data(self):
        profile = self.manager.create("Config", self.installation)
        path = self.manager.write_config_ini(profile.identifier)
        text = path.read_text(encoding="utf-8")
        self.assertIn(f"read-data={self.installation / 'data'}", text)

    def test_the_config_is_inside_the_profile(self):
        profile = self.manager.create("Config", self.installation)
        path = self.manager.write_config_ini(profile.identifier)
        self.assertTrue(str(path).startswith(str(profile.root)))

    def test_the_installation_is_never_written_to(self):
        profile = self.manager.create("Config", self.installation)
        before = sorted(str(item) for item in self.installation.rglob("*"))
        self.manager.write_config_ini(profile.identifier)
        after = sorted(str(item) for item in self.installation.rglob("*"))
        self.assertEqual(before, after)

    def test_the_profile_gets_its_own_data_directories(self):
        profile = self.manager.create("Config", self.installation)
        self.manager.write_config_ini(profile.identifier)
        for child in ("saves", "mods", "config", "script-output"):
            self.assertTrue((profile.root / child).is_dir())

    def test_two_profiles_never_share_a_write_data_directory(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        first_text = self.manager.write_config_ini(
            first.identifier).read_text(encoding="utf-8")
        second_text = self.manager.write_config_ini(
            second.identifier).read_text(encoding="utf-8")
        self.assertNotEqual(first_text, second_text)

    def test_the_cloud_sync_is_never_enabled(self):
        profile = self.manager.create("Config", self.installation)
        text = self.manager.write_config_ini(
            profile.identifier).read_text(encoding="utf-8")
        self.assertIn("enable-blueprint-storage-cloud-sync=false", text)


class FingerprintRefreshTests(ProfileManagerTestCase):
    def test_the_mods_are_re_read_on_refresh(self):
        profile = self.manager.create("Refresh", self.installation)
        refreshed = self.manager.refresh_mods(profile.identifier)
        self.assertIn("base", {mod.name for mod in refreshed.mods})

    def test_a_mod_change_changes_the_fingerprint(self):
        profile = self.manager.create("Refresh", self.installation)
        before = self.manager.fingerprint(profile.identifier)
        mods_directory = self.installation / "mods"
        folder = mods_directory / "extra_1.0.0"
        folder.mkdir()
        (folder / "info.json").write_text(
            json.dumps({"name": "extra", "version": "1.0.0"}), encoding="utf-8")
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "base", "enabled": True},
                                 {"name": "extra", "enabled": True}]}),
            encoding="utf-8")
        refreshed = self.manager.refresh_mods(profile.identifier)
        self.assertNotEqual(before, refreshed.fingerprint)

    def test_a_refresh_without_a_change_keeps_the_fingerprint(self):
        profile = self.manager.create("Refresh", self.installation)
        before = self.manager.fingerprint(profile.identifier)
        refreshed = self.manager.refresh_mods(profile.identifier)
        self.assertEqual(before, refreshed.fingerprint)


class CacheInvalidationTests(ProfileManagerTestCase):
    def test_the_caches_are_current_after_a_first_invalidation(self):
        profile = self.manager.create("Cache", self.installation)
        self.manager.invalidate_caches(profile.identifier)
        self.assertTrue(self.manager.caches_are_current(profile.identifier))

    def test_a_mod_change_makes_the_caches_stale(self):
        profile = self.manager.create("Cache", self.installation)
        self.manager.invalidate_caches(profile.identifier)
        mods_directory = self.installation / "mods"
        folder = mods_directory / "extra_1.0.0"
        folder.mkdir()
        (folder / "info.json").write_text(
            json.dumps({"name": "extra", "version": "1.0.0"}), encoding="utf-8")
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "base", "enabled": True},
                                 {"name": "extra", "enabled": True}]}),
            encoding="utf-8")
        self.manager.refresh_mods(profile.identifier)
        self.assertFalse(self.manager.caches_are_current(profile.identifier))

    def test_the_content_caches_are_dropped_on_a_change(self):
        profile = self.manager.create("Cache", self.installation)
        self.manager.invalidate_caches(profile.identifier)
        mods_directory = self.installation / "mods"
        folder = mods_directory / "extra_1.0.0"
        folder.mkdir()
        (folder / "info.json").write_text(
            json.dumps({"name": "extra", "version": "1.0.0"}), encoding="utf-8")
        (mods_directory / "mod-list.json").write_text(
            json.dumps({"mods": [{"name": "base", "enabled": True},
                                 {"name": "extra", "enabled": True}]}),
            encoding="utf-8")
        self.manager.refresh_mods(profile.identifier)
        dropped = self.manager.invalidate_caches(profile.identifier)
        self.assertEqual(
            sorted(dropped),
            ["blueprints", "machines", "recipes", "research"])

    def test_nothing_is_dropped_when_the_content_is_unchanged(self):
        profile = self.manager.create("Cache", self.installation)
        self.manager.invalidate_caches(profile.identifier)
        dropped = self.manager.invalidate_caches(profile.identifier)
        self.assertEqual(dropped, [])

    def test_the_cache_state_is_inside_the_profile(self):
        profile = self.manager.create("Cache", self.installation)
        self.manager.invalidate_caches(profile.identifier)
        self.assertTrue(
            str(self.manager.cache_state_path(profile.identifier)).startswith(
                str(profile.root)))

    def test_switching_profiles_invalidates_the_previous_caches(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        self.manager.select(first.identifier)
        self.manager.invalidate_caches(first.identifier)
        self.manager.select(second.identifier)
        # The first profile's recorded fingerprint is still its own, so a
        # later change there is still noticed.
        self.assertTrue(self.manager.caches_are_current(first.identifier))


class ProfileSessionGuardTests(ProfileManagerTestCase):
    """A profile whose game runs may not be switched away from."""

    def test_a_running_game_blocks_the_switch(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        self.manager.select(first.identifier)
        original = self.manager.session_state
        self.manager.session_state = lambda identifier: {
            "running": True, "owned": True, "pid": 1, "detail": "Running"}
        try:
            with self.assertRaises(ProfileError) as caught:
                self.manager.select(second.identifier)
            self.assertIn("still running", str(caught.exception))
        finally:
            self.manager.session_state = original

    def test_the_selection_is_unchanged_after_a_refusal(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        self.manager.select(first.identifier)
        original = self.manager.session_state
        self.manager.session_state = lambda identifier: {
            "running": True, "owned": True, "pid": 1, "detail": "Running"}
        try:
            with self.assertRaises(ProfileError):
                self.manager.select(second.identifier)
        finally:
            self.manager.session_state = original
        self.assertEqual(self.manager.selected, first.identifier)

    def test_an_idle_profile_may_be_switched(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        self.manager.select(first.identifier)
        original = self.manager.session_state
        self.manager.session_state = lambda identifier: {
            "running": False, "owned": False, "pid": None, "detail": "Not running"}
        try:
            self.manager.select(second.identifier)
        finally:
            self.manager.session_state = original
        self.assertEqual(self.manager.selected, second.identifier)

    def test_an_unreadable_session_does_not_block_the_switch(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        self.manager.select(first.identifier)
        original = self.manager.session_state
        self.manager.session_state = lambda identifier: None
        try:
            self.manager.select(second.identifier)
        finally:
            self.manager.session_state = original
        self.assertEqual(self.manager.selected, second.identifier)

    def test_switching_to_the_same_profile_is_never_blocked(self):
        first = self.manager.create("First", self.installation)
        self.manager.select(first.identifier)
        original = self.manager.session_state
        self.manager.session_state = lambda identifier: {
            "running": True, "owned": True, "pid": 1, "detail": "Running"}
        try:
            self.manager.select(first.identifier)
        finally:
            self.manager.session_state = original
        self.assertEqual(self.manager.selected, first.identifier)

    def test_the_session_state_of_a_missing_profile_is_empty(self):
        self.assertIsNone(self.manager.session_state("does-not-exist"))

    def test_the_first_selection_of_a_running_profile_is_refused(self):
        profile = self.manager.create("Running", self.installation)
        original = self.manager.session_state
        self.manager.session_state = lambda identifier: {
            "running": True, "owned": True, "pid": 1, "detail": "Running"}
        try:
            with self.assertRaises(ProfileError):
                self.manager.select(profile.identifier)
        finally:
            self.manager.session_state = original
        self.assertIsNone(self.manager.selected)


class ProfileSwitchIsolationTests(ProfileManagerTestCase):
    def test_switching_does_not_change_the_mod_configuration(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        self.manager.select(first.identifier)
        self.manager.select(second.identifier)
        self.assertEqual(
            self.manager.load(first.identifier).mods_directory,
            self.manager.load(second.identifier).mods_directory)

    def test_switching_never_moves_a_save(self):
        first = self.manager.create("First", self.installation)
        second = self.manager.create("Second", self.installation)
        (first.saves_directory / "world.zip").write_bytes(b"one")
        self.manager.select(first.identifier)
        self.manager.select(second.identifier)
        self.assertTrue((first.saves_directory / "world.zip").is_file())
        self.assertFalse((second.saves_directory / "world.zip").exists())

    def test_switching_to_an_unknown_profile_is_refused(self):
        with self.assertRaises(ProfileError):
            self.manager.select("does-not-exist")


PROFILE_FILE_NAME = PROFILE_FILE


if __name__ == "__main__":
    unittest.main()
