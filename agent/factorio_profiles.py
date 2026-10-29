"""Universal Factorio profile management for the AutoEngineer launcher.

A *profile* is one Factorio installation plus one mod configuration plus
its own saves, configuration and caches. The user creates, edits, renames,
duplicates, imports, selects and deletes profiles.

This module is deliberately **not** limited to Vanilla, Space Age or
Pyanodons. Those are only two test profiles; any compatible modpack is a
first-class profile. Nothing in this module knows the name of a mod, a
recipe, a machine or a technology, and no prototype data is embedded
anywhere: every mod fact is read from the installation's own
``mod-list.json`` and from the ``info.json`` of the mod folders that are
actually present.

What this module does **not** do:

* it never starts Factorio. Launching, stopping and restarting are the
  business of the supervised service in ``launcher_services``;
* it never writes into an installation. A profile only records *paths*;
* it never stores a credential. API keys, RCON passwords and model
  secrets stay in the environment or in the separate secret files.

The storage layout is one directory per profile under the profile root,
each with a ``profile.json`` and its own ``saves``, ``config`` and
``cache`` directories. The profile root defaults to
``.local/factorio-profiles`` inside the project, and every path is stored
absolutely so a profile can be moved or inspected from anywhere.

Every write is atomic: the JSON is written to a temporary file in the same
directory and then renamed over the target, so an interrupted write can
never leave a half-written profile behind.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

#: The Factorio version this AutoEngineer build supports.
SUPPORTED_GAME_VERSION = "2.1.23"

#: The profile file name inside a profile directory.
PROFILE_FILE = "profile.json"

#: The directories every profile owns.
PROFILE_DIRECTORIES = ("saves", "config", "cache")

#: A profile name has to be usable as a directory name on Windows and as
#: a readable label in the interface.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")

#: The maximum number of profiles one root may hold. The interface has to
#: stay responsive, and a larger set is a sign that the user needs folders.
MAX_PROFILES = 128

#: The maximum number of mods one profile may record.
MAX_MODS = 4096


class ProfileError(ValueError):
    """The profile data was not valid, or the operation was refused."""


@dataclass(frozen=True)
class ModInfo:
    """One mod the installation declares.

    ``name`` and ``version`` come from the mod's own ``info.json`` when
    the folder is present. A mod that the list enables but that is not
    installed on disk is reported with ``version=None`` and
    ``installed=False`` instead of being hidden, because a missing mod is
    exactly what the user has to see.
    """

    name: str
    enabled: bool
    version: str | None = None
    installed: bool = False
    dependencies: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "version": self.version,
            "installed": self.installed,
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True)
class Installation:
    """A detected Factorio installation.

    ``usable`` means the directory holds a Factorio executable, so the
    user can actually play here. That is a different question from
    ``game_version``: an installation whose version cannot be read is
    still usable, and the version is reported as unknown instead of
    blocking the profile.
    """

    root: Path
    executable: Path
    game_version: str | None
    version_source: str
    valid: bool
    problem: str | None = None
    usable: bool = False
    version_problem: str | None = None

    @property
    def display_version(self) -> str:
        return self.game_version or "unknown"

    @property
    def supported(self) -> bool:
        return self.game_version == SUPPORTED_GAME_VERSION


@dataclass(frozen=True)
class Profile:
    """One stored profile."""

    identifier: str
    name: str
    root: Path
    installation_root: Path
    executable: Path
    mods_directory: Path
    saves_directory: Path
    config_directory: Path
    cache_directory: Path
    game_version: str | None
    notes: str = ""
    mods: tuple[ModInfo, ...] = field(default_factory=tuple)

    @property
    def enabled_mods(self) -> tuple[ModInfo, ...]:
        return tuple(mod for mod in self.mods if mod.enabled)

    @property
    def fingerprint(self) -> str:
        """The identity of this profile's content.

        The fingerprint covers the game version and the authoritative mod
        identity: the name, the enabled flag, the version and the
        dependency list of every mod the installation declares. Two
        profiles with the same fingerprint have the same observable
        content, so a cached catalog may be reused between them.
        """
        digest = hashlib.sha256()
        digest.update((self.game_version or "unknown").encode("utf-8"))
        for mod in sorted(self.mods, key=lambda item: item.name):
            digest.update(b"\0")
            digest.update(mod.name.encode("utf-8"))
            digest.update(b"\1" if mod.enabled else b"\0")
            digest.update((mod.version or "").encode("utf-8"))
            for dependency in mod.dependencies:
                digest.update(b"\0")
                digest.update(dependency.encode("utf-8"))
        return digest.hexdigest()

    @property
    def missing_mods(self) -> tuple[str, ...]:
        """The enabled mods that are not installed on disk."""
        return tuple(
            mod.name for mod in self.mods if mod.enabled and not mod.installed)

    @property
    def unsatisfied_dependencies(self) -> tuple[str, ...]:
        """The enabled mods whose dependencies are not enabled."""
        enabled = {mod.name for mod in self.mods if mod.enabled}
        problems: list[str] = []
        for mod in self.mods:
            if not mod.enabled:
                continue
            for dependency in mod.dependencies:
                match = re.match(r"^\s*(?:[?~!]\s*)?([A-Za-z0-9_-]+)", dependency)
                if not match:
                    continue
                required = match.group(1)
                if dependency.lstrip().startswith("!"):
                    if required in enabled:
                        problems.append(f"{mod.name} conflicts with {required}")
                elif dependency.lstrip().startswith(("?", "~")):
                    continue
                elif required not in enabled:
                    problems.append(f"{mod.name} requires {required}")
        return tuple(problems)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "identifier": self.identifier,
            "name": self.name,
            "installation_root": str(self.installation_root),
            "executable": str(self.executable),
            "mods_directory": str(self.mods_directory),
            "saves_directory": str(self.saves_directory),
            "config_directory": str(self.config_directory),
            "cache_directory": str(self.cache_directory),
            "game_version": self.game_version,
            "notes": self.notes,
            "mods": [mod.to_dict() for mod in self.mods],
        }


def default_profile_root() -> Path:
    """Return the default directory that holds the profiles."""
    override = os.environ.get("AUTOENGINEER_PROFILE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parents[1]
            / ".local" / "factorio-profiles").resolve()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON atomically, so a failed write cannot corrupt the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_json(path: Path) -> Any:
    """Read JSON, raising a clear error when the file is unusable."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ProfileError(f"Cannot read {path}: {error}") from None
    except ValueError as error:
        raise ProfileError(f"{path} is not valid JSON: {error}") from None


def validate_name(name: Any) -> str:
    """Return a valid profile name or refuse."""
    if not isinstance(name, str):
        raise ProfileError("The profile name must be text")
    candidate = name.strip()
    if not candidate:
        raise ProfileError("The profile name must not be empty")
    if not NAME_PATTERN.fullmatch(candidate):
        raise ProfileError(
            "The profile name may use letters, digits, spaces, dots, "
            "underscores and dashes, and must start with a letter or digit")
    if candidate in {".", ".."}:
        raise ProfileError("The profile name is not usable")
    return candidate


def _slug(name: str) -> str:
    """Return a filesystem-safe identifier derived from a profile name."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").lower()
    return slug[:48] or "profile"


# ---------------------------------------------------------------------------
# Installation detection
# ---------------------------------------------------------------------------

#: The places a Factorio installation is looked for when the user has not
#: selected one manually.
COMMON_INSTALLATION_ROOTS: tuple[Path, ...] = (
    Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Factorio"),
    Path(r"C:\Program Files\Factorio"),
    Path(r"C:\Program Files (x86)\Factorio"),
    Path(r"C:\Program Files\Factorio Factory"),
    Path(r"C:\Program Files (x86)\Factorio Factory"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Factorio Factory"),
)


def executable_candidates(root: Path) -> tuple[Path, ...]:
    """Return the possible Factorio executables inside an installation."""
    return (
        root / "bin" / "x64" / "factorio.exe",
        root / "bin" / "x64" / "factorio-debug.exe",
        root / "factorio.exe",
        root / "factorio",
    )


def read_executable_version(executable: Path) -> tuple[str | None, str]:
    """Return the game version of an executable and where it came from.

    The version is read from the Windows file-version resource, which is
    what the isolated installation was verified with. On a platform that
    has no such resource, and for a file that carries no version, the
    version is ``None`` and the source says so. A version is never
    guessed from the directory name, because the directory name is
    routinely stale: the verified 2.1.23 install lives in a directory
    called ``Factorio_2.1.22``.
    """
    if not executable.is_file():
        return None, "missing"
    if os.name == "nt":
        try:
            import win32api  # type: ignore[import-not-found]

            info = win32api.GetFileVersionInfo(str(executable), "\\")
            ms = info["FileVersionMS"]
            ls = info["FileVersionLS"]
            version = (
                f"{(ms >> 16) & 0xFFFF}.{ms & 0xFFFF}."
                f"{(ls >> 16) & 0xFFFF}.{ls & 0xFFFF}"
            )
            if version.rstrip(".0") == version:
                version = version.rsplit(".", 1)[0]
            return version, "file-version"
        except Exception:  # pragma: no cover - depends on the platform
            pass
        try:
            import ctypes
            from ctypes import wintypes  # noqa: F401

            size = ctypes.windll.version.GetFileVersionInfoSizeW(
                str(executable), None)
            if size:
                buffer = ctypes.create_string_buffer(size)
                ctypes.windll.version.GetFileVersionInfoW(
                    str(executable), 0, size, buffer)
                info = ctypes.windll.version.VerQueryValueW(
                    buffer, "\\", ctypes.byref(ctypes.c_uint()), ctypes.byref(ctypes.c_uint()))
                ms = info[3]
                ls = info[4]
                version = (
                    f"{(ms >> 16) & 0xFFFF}.{ms & 0xFFFF}."
                    f"{(ls >> 16) & 0xFFFF}.{ls & 0xFFFF}"
                )
                return version, "file-version"
        except Exception:  # pragma: no cover - depends on the platform
            pass
    return None, "unavailable"


def detect_installation(root: Path) -> Installation:
    """Inspect a directory and report the Factorio installation it holds.

    The result is honest about what it knows: a directory without a
    Factorio executable is reported as invalid with the reason, and a
    version that could not be read is reported as ``None`` rather than
    being filled in from the directory name.
    """
    root = Path(root).expanduser()
    try:
        root = root.resolve()
    except OSError:
        return Installation(root, root / "bin" / "x64" / "factorio.exe",
                            None, "unresolved", False,
                            "The installation directory cannot be resolved",
                            False)
    if not root.is_dir():
        return Installation(root, root / "bin" / "x64" / "factorio.exe",
                            None, "unresolved", False,
                            "The installation directory does not exist",
                            False)
    for candidate in executable_candidates(root):
        if candidate.is_file():
            version, source = read_executable_version(candidate)
            version_problem = None
            if version is None:
                version_problem = ("The game version could not be read from "
                                   "the executable")
            elif version != SUPPORTED_GAME_VERSION:
                version_problem = (f"Factorio {version} is installed; this "
                                   f"build supports {SUPPORTED_GAME_VERSION}")
            # The installation is usable whenever the executable exists.
            # The version is reported separately, so an unreadable version
            # never blocks a profile the user can actually play.
            return Installation(root, candidate, version, source,
                                version_problem is None, version_problem,
                                True, version_problem)
    return Installation(root, root / "bin" / "x64" / "factorio.exe",
                        None, "absent", False,
                        "No Factorio executable was found in this directory",
                        False)


def discover_installations(
    extra_roots: tuple[Path, ...] = (),
) -> list[Installation]:
    """Return every Factorio installation that can be found.

    The common locations are searched and the results are de-duplicated by
    the resolved installation root. A manually selected directory is
    always included, even when it is outside the common locations.

    A directory that does not hold Factorio is **not** an installation
    and is not listed. The common locations are candidates, and most
    machines have only one or two of them, so reporting the missing ones
    as broken would be noise.
    """
    seen: set[str] = set()
    found: list[Installation] = []
    for root in tuple(extra_roots) + COMMON_INSTALLATION_ROOTS:
        installation = detect_installation(root)
        key = str(installation.root).lower()
        if key in seen:
            continue
        seen.add(key)
        if not installation.root.is_dir():
            continue
        if installation.executable.is_file():
            found.append(installation)
    return found


# ---------------------------------------------------------------------------
# Mod reading
# ---------------------------------------------------------------------------

def read_mod_list(
    mods_directory: Path, installation_root: Path | None = None
) -> tuple[ModInfo, ...]:
    """Read the installation's own ``mod-list.json`` and the mod folders.

    The list declares which mods are enabled. The folders on disk declare
    the versions and the dependencies. Both are needed: a mod that is
    enabled but not installed is a real problem the user has to see, and a
    mod folder that is not in the list is not part of the configuration.
    """
    mods_directory = Path(mods_directory)
    if not mods_directory.is_dir():
        return ()
    list_path = mods_directory / "mod-list.json"
    declared: dict[str, bool] = {}
    if list_path.is_file():
        document = _read_json(list_path)
        if isinstance(document, Mapping):
            entries = document.get("mods")
            if isinstance(entries, list) and len(entries) <= MAX_MODS:
                for entry in entries:
                    if not isinstance(entry, Mapping):
                        continue
                    name = entry.get("name")
                    if isinstance(name, str) and name:
                        declared[name] = entry.get("enabled") is True
    versions: dict[str, tuple[str | None, tuple[str, ...]]] = {}

    def record(info: Any) -> None:
        if not isinstance(info, Mapping):
            return
        name = info.get("name")
        if not isinstance(name, str) or not name:
            return
        version = info.get("version")
        dependencies = info.get("dependencies")
        dependency_names = tuple(
            item for item in dependencies if isinstance(item, str)
        ) if isinstance(dependencies, list) else ()
        versions[name] = (
            version if isinstance(version, str) else None,
            dependency_names,
        )

    # Built-in mods live in the game's data directory, not the mods folder.
    installation_data = (installation_root or mods_directory.parent) / "data"
    if installation_data.is_dir():
        for folder in installation_data.iterdir():
            if (folder / "info.json").is_file():
                try:
                    record(_read_json(folder / "info.json"))
                except ProfileError:
                    continue

    for entry in sorted(mods_directory.iterdir()):
        if entry.is_dir():
            if (entry / "info.json").is_file():
                try:
                    record(_read_json(entry / "info.json"))
                except ProfileError:
                    continue
        elif entry.is_file() and entry.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(entry) as archive:
                    info_names = [
                        name for name in archive.namelist()
                        if len(name.split("/")) == 2
                        and name.endswith("/info.json")
                    ]
                    if len(info_names) == 1:
                        record(json.loads(archive.read(info_names[0])))
            except (OSError, zipfile.BadZipFile, ValueError, UnicodeError):
                continue
    mods: list[ModInfo] = []
    for name in sorted(set(declared) | set(versions)):
        enabled = declared.get(name, False)
        version, dependencies = versions.get(name, (None, ()))
        mods.append(ModInfo(
            name=name,
            enabled=enabled,
            version=version,
            installed=name in versions,
            dependencies=dependencies,
        ))
    return tuple(mods)


# ---------------------------------------------------------------------------
# Profile storage
# ---------------------------------------------------------------------------

class ProfileManager:
    """The stored profiles of one profile root.

    The manager owns the directory layout, the validation of every write
    and the fingerprinting of the content. It never starts a process and
    never touches a save.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_profile_root()
        self.root = self.root.expanduser()
        self._selected: str | None = None

    # -- reading ---------------------------------------------------------

    def profile_directories(self) -> list[Path]:
        """Return every profile directory, sorted by name."""
        if not self.root.is_dir():
            return []
        directories = [
            entry for entry in self.root.iterdir()
            if entry.is_dir() and (entry / PROFILE_FILE).is_file()
        ]
        return sorted(directories, key=lambda item: item.name.lower())

    def identifiers(self) -> list[str]:
        """Return the identifiers of every stored profile."""
        return [directory.name for directory in self.profile_directories()]

    def load(self, identifier: str) -> Profile:
        """Return one stored profile, or refuse."""
        if not isinstance(identifier, str) or not identifier:
            raise ProfileError("A profile identifier is required")
        if "/" in identifier or "\\" in identifier or identifier in {".", ".."}:
            raise ProfileError("The profile identifier is not usable")
        directory = self.root / identifier
        document = _read_json(directory / PROFILE_FILE)
        return self._profile_from_document(document, directory)

    def list_profiles(self) -> list[Profile]:
        """Return every stored profile that can be read."""
        profiles: list[Profile] = []
        for directory in self.profile_directories():
            try:
                profiles.append(self._profile_from_document(
                    _read_json(directory / PROFILE_FILE), directory))
            except ProfileError:
                continue
        return profiles

    def _profile_from_document(
            self, document: Any, directory: Path) -> Profile:
        if not isinstance(document, Mapping):
            raise ProfileError("The profile file is not a JSON object")
        if document.get("schema") != 1:
            raise ProfileError("The profile file has an unsupported schema")
        name = validate_name(document.get("name"))
        identifier = document.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise ProfileError("The profile file has no identifier")
        if identifier != directory.name:
            raise ProfileError("The profile identifier does not match its folder")
        mods = tuple(
            ModInfo(
                name=str(entry.get("name")),
                enabled=entry.get("enabled") is True,
                version=entry.get("version")
                if isinstance(entry.get("version"), str) else None,
                installed=entry.get("installed") is True,
                dependencies=tuple(
                    str(item) for item in (entry.get("dependencies") or [])
                    if isinstance(item, str)),
            )
            for entry in (document.get("mods") or [])
            if isinstance(entry, Mapping) and isinstance(entry.get("name"), str)
        )
        notes = document.get("notes")
        return Profile(
            identifier=identifier,
            name=name,
            root=directory,
            installation_root=Path(str(document.get("installation_root", ""))),
            executable=Path(str(document.get("executable", ""))),
            mods_directory=Path(str(document.get("mods_directory", ""))),
            saves_directory=Path(str(document.get("saves_directory", ""))),
            config_directory=Path(str(document.get("config_directory", ""))),
            cache_directory=Path(str(document.get("cache_directory", ""))),
            game_version=document.get("game_version")
            if isinstance(document.get("game_version"), str) else None,
            notes=notes if isinstance(notes, str) else "",
            mods=mods,
        )

    # -- writing ---------------------------------------------------------

    def _unique_identifier(self, name: str) -> str:
        base = _slug(name)
        existing = set(self.identifiers())
        if base not in existing:
            return base
        for suffix in range(2, 1000):
            candidate = f"{base}-{suffix}"
            if candidate not in existing:
                return candidate
        raise ProfileError("No free profile identifier could be found")

    def create(
            self,
            name: str,
            installation_root: Path,
            *,
            notes: str = "",
            mods_directory: Path | None = None,
    ) -> Profile:
        """Create a new profile for an installation.

        The profile owns its own saves, configuration and cache
        directories, so switching profiles can never mix one profile's
        saves with another's. The installation itself is only *read*.
        """
        if len(self.profile_directories()) >= MAX_PROFILES:
            raise ProfileError(
                f"This root already holds the maximum of {MAX_PROFILES} profiles")
        valid_name = validate_name(name)
        installation = detect_installation(Path(installation_root))
        if not installation.usable:
            raise ProfileError(
                installation.problem or "The installation is not usable")
        identifier = self._unique_identifier(valid_name)
        directory = self.root / identifier
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise ProfileError("The profile folder already exists") from None
        for child in PROFILE_DIRECTORIES:
            (directory / child).mkdir(parents=True, exist_ok=True)
        resolved_mods = Path(mods_directory) if mods_directory is not None \
            else installation.root / "mods"
        profile = Profile(
            identifier=identifier,
            name=valid_name,
            root=directory,
            installation_root=installation.root,
            executable=installation.executable,
            mods_directory=resolved_mods,
            saves_directory=directory / "saves",
            config_directory=directory / "config",
            cache_directory=directory / "cache",
            game_version=installation.game_version,
            notes=notes,
            mods=read_mod_list(resolved_mods, installation.root),
        )
        self._write(profile)
        # The profile that was just created becomes the selected one, so
        # the application shows it without the user having to select it.
        # The profile is new, so it cannot have a running game and the
        # session guard does not apply.
        self._selected = profile.identifier
        self._write_selection(profile.identifier)
        return profile

    def _write(self, profile: Profile) -> None:
        _atomic_write_json(profile.root / PROFILE_FILE, profile.to_dict())

    # -- the per-profile configuration ------------------------------------

    def write_config_ini(self, identifier: str) -> Path:
        """Write the profile's own ``config.ini`` and return its path.

        The file points Factorio at the profile's **own** write-data
        directory, so the profile's saves, mods and configuration are its
        own and never another profile's. The read-data directory is the
        installation's data directory, which is where the game and the mods
        live.

        The file is written **inside the profile's own config directory**.
        The installation is never written to.
        """
        profile = self.load(identifier)
        installation = detect_installation(profile.installation_root)
        if not installation.usable:
            raise ProfileError(
                installation.problem or "The installation is not usable")
        # Factorio writes saves to write-data/saves; use the profile root
        # so that this matches Profile.saves_directory exactly.
        data_root = profile.root
        for child in ("saves", "mods", "config", "script-output"):
            (data_root / child).mkdir(parents=True, exist_ok=True)
        # The profile's own mods directory is linked into its write-data
        # directory, so the game sees exactly the mods this profile
        # declares. The junction is only created when the directory is
        # empty, so an existing folder is never overwritten.
        mods_target = profile.mods_directory
        mods_link = data_root / "mods"
        if mods_target.is_dir() and not mods_link.exists():
            try:
                mods_link.symlink_to(mods_target, target_is_directory=True)
            except (OSError, NotImplementedError):
                # A junction needs the Windows rights; without it the
                # profile still works, it just uses the default mods.
                pass
        config_path = profile.config_directory / "config.ini"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "[path]\n"
            f"read-data={installation.root / 'data'}\n"
            f"write-data={data_root}\n"
            "\n"
            "[other]\n"
            "check-updates=false\n"
            "enable-crash-log-uploading=false\n"
            "enable-blueprint-storage-cloud-sync=false\n",
            encoding="utf-8")
        return config_path

    def refresh_mods(self, identifier: str) -> Profile:
        """Re-read the profile's mods and store the new fingerprint.

        The fingerprint covers the game version and the authoritative mod
        identity. When the mods change, the fingerprint changes, and a
        cached catalog of the old content is therefore invalid.
        """
        profile = self.load(identifier)
        mods = read_mod_list(profile.mods_directory, profile.installation_root)
        refreshed = Profile(
            identifier=profile.identifier,
            name=profile.name,
            root=profile.root,
            installation_root=profile.installation_root,
            executable=profile.executable,
            mods_directory=profile.mods_directory,
            saves_directory=profile.saves_directory,
            config_directory=profile.config_directory,
            cache_directory=profile.cache_directory,
            game_version=profile.game_version,
            notes=profile.notes,
            mods=mods,
        )
        self._write(refreshed)
        return refreshed

    def fingerprint(self, identifier: str) -> str:
        """Return the fingerprint of the profile's current content."""
        return self.load(identifier).fingerprint

    def cache_state_path(self, identifier: str) -> Path:
        """Return the file that records the profile's cached content.

        The file holds the fingerprint the caches were filled with. When
        the profile's mods change, the fingerprint no longer matches and
        the caches are invalidated.
        """
        profile = self.load(identifier)
        return profile.cache_directory / "content.json"

    def read_cache_state(self, identifier: str) -> dict[str, Any]:
        """Return the recorded cache state of a profile."""
        path = self.cache_state_path(identifier)
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}
        return document if isinstance(document, dict) else {}

    def invalidate_caches(self, identifier: str) -> list[str]:
        """Invalidate the caches of a profile and report what was dropped.

        The **recipe, machine, research and blueprint** caches all depend
        on the observed content, so they are dropped together when the
        content changes. The recorded fingerprint is updated, so the next
        read fills the caches again from the new content.
        """
        profile = self.load(identifier)
        current = profile.fingerprint
        state = self.read_cache_state(identifier)
        previous = state.get("fingerprint")
        dropped: list[str] = []
        if previous is not None and previous != current:
            dropped = ["recipes", "machines", "research", "blueprints"]
        profile.cache_directory.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.cache_state_path(identifier), {
            "fingerprint": current,
            "game_version": profile.game_version,
            "mods": [mod.to_dict() for mod in profile.mods],
        })
        return dropped

    def caches_are_current(self, identifier: str) -> bool:
        """Whether the recorded caches still match the profile's content."""
        state = self.read_cache_state(identifier)
        if not state:
            return False
        return state.get("fingerprint") == self.fingerprint(identifier)

    def update(self, identifier: str, **changes: Any) -> Profile:
        """Change the editable fields of a profile.

        Only the name, the notes and the installation path may be
        changed. The owned directories and the identifier are immutable,
        because moving a profile's saves under another profile would mix
        two configurations.
        """
        profile = self.load(identifier)
        name = validate_name(changes.get("name", profile.name))
        notes = changes.get("notes", profile.notes)
        if not isinstance(notes, str) or len(notes) > 2000:
            raise ProfileError("The profile notes must be text of at most 2000 characters")
        installation_root = changes.get(
            "installation_root", profile.installation_root)
        installation = detect_installation(Path(installation_root))
        if not installation.usable:
            raise ProfileError(
                installation.problem or "The installation is not usable")
        updated = Profile(
            identifier=profile.identifier,
            name=name,
            root=profile.root,
            installation_root=installation.root,
            executable=installation.executable,
            mods_directory=profile.mods_directory,
            saves_directory=profile.saves_directory,
            config_directory=profile.config_directory,
            cache_directory=profile.cache_directory,
            game_version=installation.game_version,
            notes=notes,
            mods=profile.mods,
        )
        self._write(updated)
        return updated

    def rename(self, identifier: str, name: str) -> Profile:
        """Rename a profile without changing its identifier."""
        return self.update(identifier, name=name)

    def duplicate(self, identifier: str, name: str | None = None) -> Profile:
        """Copy a profile, including its saves, configuration and cache.

        The copy is a **separate** profile: it owns its own directories,
        so the two never share a save. The installation is shared, because
        it is the user's Factorio installation and not the profile's.
        """
        source = self.load(identifier)
        target_name = validate_name(name if name else f"{source.name} copy")
        if len(self.profile_directories()) >= MAX_PROFILES:
            raise ProfileError(
                f"This root already holds the maximum of {MAX_PROFILES} profiles")
        target_identifier = self._unique_identifier(target_name)
        target = self.root / target_identifier
        try:
            target.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise ProfileError("The profile folder already exists") from None
        for child in PROFILE_DIRECTORIES:
            (target / child).mkdir(parents=True, exist_ok=True)
        for child in PROFILE_DIRECTORIES:
            origin = source.root / child
            if not origin.is_dir():
                continue
            for item in origin.iterdir():
                destination = target / child / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                elif item.is_file():
                    shutil.copy2(item, destination)
        copy = Profile(
            identifier=target_identifier,
            name=target_name,
            root=target,
            installation_root=source.installation_root,
            executable=source.executable,
            mods_directory=source.mods_directory,
            saves_directory=target / "saves",
            config_directory=target / "config",
            cache_directory=target / "cache",
            game_version=source.game_version,
            notes=source.notes,
            mods=source.mods,
        )
        self._write(copy)
        return copy

    def import_profile(self, source_file: Path) -> Profile:
        """Import a profile from an exported profile file.

        The imported profile gets its own identifier and its own
        directories, so importing never overwrites an existing profile.
        """
        document = _read_json(Path(source_file))
        if not isinstance(document, Mapping):
            raise ProfileError("The imported file is not a JSON object")
        name = validate_name(document.get("name"))
        installation_root = document.get("installation_root")
        if not isinstance(installation_root, str) or not installation_root:
            raise ProfileError("The imported profile has no installation path")
        return self.create(
            name, Path(installation_root),
            notes=str(document.get("notes") or ""),
            mods_directory=Path(str(document.get("mods_directory")))
            if document.get("mods_directory") else None,
        )

    def export_profile(self, identifier: str, destination: Path) -> Path:
        """Write a profile's definition to a file that can be imported."""
        profile = self.load(identifier)
        destination = Path(destination)
        _atomic_write_json(destination, profile.to_dict())
        return destination

    def delete(self, identifier: str, *, confirm: bool = False) -> None:
        """Delete a profile and everything it owns.

        The deletion has to be confirmed explicitly, and it removes the
        profile's own saves, configuration and cache. The Factorio
        installation is never touched: it belongs to the user, not to the
        profile.
        """
        if confirm is not True:
            raise ProfileError("Deleting a profile has to be confirmed")
        profile = self.load(identifier)
        if profile.root.parent != self.root.resolve() \
                and profile.root.parent != self.root:
            raise ProfileError("The profile folder is outside the profile root")
        shutil.rmtree(profile.root)

    # -- selection -------------------------------------------------------

    @property
    def selected(self) -> str | None:
        """The identifier of the selected profile, if any."""
        return self._selected

    def select(self, identifier: str | None) -> str | None:
        """Select a profile, or clear the selection.

        Selecting a profile never modifies it and never modifies another
        profile. The selection is remembered in the profile root so the
        next start of the application opens on the same profile.

        Switching **invalidates the caches** of the profile that is being
        left, because its observations belong to a different game state.
        The caches of the profile that is being entered are checked
        against its own fingerprint, so a content change is noticed
        instead of serving a stale catalog.

        A switch is **refused** while the profile that is being left has
        a running game: the game belongs to that profile, and switching
        away would leave the application watching one profile while the
        game runs with another. The caller stops the game first.
        """
        if identifier is None:
            self._selected = None
            self._write_selection(None)
            return None
        profile = self.load(identifier)
        previous = self._selected
        if previous == profile.identifier:
            # Selecting the profile that is already selected changes
            # nothing, so it is not refused even while its game runs.
            return profile.identifier
        if previous is not None:
            self._require_idle(previous)
        # The profile that is being entered may have a running game of its
        # own, for example after the application was restarted while the
        # game stayed open. Selecting it would then put the application
        # in front of a game it does not own.
        self._require_idle(profile.identifier)
        if previous is not None:
            try:
                self.invalidate_caches(previous)
            except ProfileError:
                # The profile that is being left is already unreadable;
                # that is not a reason to refuse the switch.
                pass
        self._selected = profile.identifier
        self._write_selection(profile.identifier)
        try:
            self.invalidate_caches(profile.identifier)
        except ProfileError:
            pass
        return profile.identifier

    def _require_idle(self, identifier: str) -> None:
        """Refuse a switch while the profile's game is running.

        The check is read-only: it asks the game session for its state
        and never starts, stops or changes a game.
        """
        state = self.session_state(identifier)
        if state is None:
            return
        running = bool(state.get("running")) if isinstance(state, Mapping) else False
        if running:
            raise ProfileError(
                "The profile's game is still running; stop it before "
                "switching to another profile")

    def session_state(self, identifier: str) -> Mapping[str, Any] | None:
        """Return the state of the profile's game session, if it has one.

        The state is read from the live session. A profile whose session
        cannot be inspected reports nothing, so a broken session never
        blocks the user.
        """
        try:
            from factorio_session import GameSession

            profile = self.load(identifier)
        except Exception:
            return None
        try:
            state = GameSession(profile).state()
        except Exception:
            return None
        return {
            "running": bool(state.running),
            "owned": bool(state.owned),
            "pid": state.pid,
            "detail": state.detail,
        }

    def _selection_path(self) -> Path:
        return self.root / "selected.json"

    def _write_selection(self, identifier: str | None) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(
                self._selection_path(), {"selected": identifier})
        except OSError:
            # A missing selection is not an error: the application simply
            # starts without a profile.
            pass

    def restore_selection(self) -> str | None:
        """Restore the selection that was stored in the profile root."""
        path = self._selection_path()
        if path.is_file():
            try:
                document = _read_json(path)
            except ProfileError:
                document = None
            if isinstance(document, Mapping):
                identifier = document.get("selected")
                if isinstance(identifier, str):
                    try:
                        self.load(identifier)
                    except ProfileError:
                        identifier = None
                    if isinstance(identifier, str):
                        self._selected = identifier
                        return identifier
        self._selected = None
        return None

    # -- diagnostics -----------------------------------------------------

    def validate(self, identifier: str) -> list[str]:
        """Return the problems of one profile.

        The list is empty when the profile is usable. Every problem is a
        sentence the interface can show as it is.
        """
        problems: list[str] = []
        try:
            profile = self.load(identifier)
        except ProfileError as error:
            return [str(error)]
        installation = detect_installation(profile.installation_root)
        if not installation.usable:
            problems.append(
                installation.problem or "The Factorio installation is not usable")
        elif installation.version_problem:
            # The installation works, but the version is not the one this
            # build supports. That is a warning about the content, not a
            # broken profile, so it is reported as a problem the user has
            # to see before the profile is used.
            problems.append(installation.version_problem)
        elif profile.game_version != installation.game_version:
            problems.append(
                "The recorded game version differs from the installation")
        for missing in profile.missing_mods:
            problems.append(f"The mod {missing} is enabled but not installed")
        for unmet in profile.unsatisfied_dependencies:
            problems.append(unmet)
        for directory in (profile.saves_directory, profile.config_directory,
                          profile.cache_directory):
            if not directory.is_dir():
                problems.append(
                    f"The profile directory {directory.name} is missing")
        return problems

    def status(self, identifier: str) -> dict[str, Any]:
        """Return a truthful, JSON-safe status of one profile."""
        try:
            profile = self.load(identifier)
        except ProfileError as error:
            return {"identifier": identifier, "readable": False,
                    "problem": str(error), "problems": [str(error)]}
        installation = detect_installation(profile.installation_root)
        return {
            "identifier": profile.identifier,
            "name": profile.name,
            "readable": True,
            "game_version": profile.game_version,
            "supported_version": SUPPORTED_GAME_VERSION,
            "version_ok": profile.game_version == SUPPORTED_GAME_VERSION,
            "installation_valid": installation.usable,
            "installation_problem": installation.problem,
            "version_problem": installation.version_problem,
            "enabled_mods": len(profile.enabled_mods),
            "missing_mods": list(profile.missing_mods),
            "unsatisfied_dependencies": list(profile.unsatisfied_dependencies),
            "fingerprint": profile.fingerprint,
            "problems": self.validate(identifier),
        }
