"""The Save Manager: the real saves of a profile, and safe operations on them.

A Factorio save is a ZIP archive that holds a `level.dat` with the
information the game wrote about the world. This module reads that
information, it never invents it, and it performs the file operations
that the Save Manager offers.

Three rules shape everything here.

**Only the selected profile's own saves are visible.** Every path is
resolved inside the profile's own saves directory. A name that would
escape it — ``..``, an absolute path, a symbolic link out of the tree — is
refused before anything is touched.

**A file is never replaced silently.** A write goes to a temporary file in
the same directory and is then renamed over the target, so an
interrupted operation leaves the original save intact. A delete needs an
explicit confirmation, and a rename refuses to overwrite an existing
save.

**A metadata field that Factorio does not expose stays empty.** The
mod list of a save is only reported when the archive really carries it.

The module contains no Qt import and starts no game, so the whole save
path is verifiable offline.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

#: The save file name Factorio writes inside the archive.
LEVEL_NAME = "level.dat"

#: A save name that is safe on Windows and readable in the interface.
SAVE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")

#: The largest save file the manager will read the metadata of.
MAX_SAVE_BYTES = 4 * 1024 * 1024 * 1024

#: The suffix the manager gives a backup.
BACKUP_SUFFIX = ".backup"

#: The name of the folder that holds the backups.
BACKUP_FOLDER = "backups"


class SaveError(RuntimeError):
    """A save operation was refused or could not be completed."""


@dataclass(frozen=True)
class SaveInfo:
    """What is really known about one save file."""

    name: str
    path: Path
    size_bytes: int
    modified: str
    game_version: str | None
    mod_list: tuple[str, ...]
    session_time: str | None
    play_time: str | None
    backups: tuple[str, ...]
    problem: str | None = None

    @property
    def readable(self) -> bool:
        """Whether the archive could be read."""
        return self.problem is None

    @property
    def display_size(self) -> str:
        """The size in a form the interface shows."""
        return format_size(self.size_bytes)

    def as_dict(self) -> dict[str, Any]:
        """Return the information as a JSON-safe dictionary."""
        return {
            "name": self.name,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "display_size": self.display_size,
            "modified": self.modified,
            "game_version": self.game_version,
            "mod_list": list(self.mod_list),
            "session_time": self.session_time,
            "play_time": self.play_time,
            "backups": list(self.backups),
            "problem": self.problem,
            "readable": self.readable,
        }


def format_size(size_bytes: int) -> str:
    """Return a byte count in the form the interface shows."""
    if type(size_bytes) is not int or size_bytes < 0:
        return "—"
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def validate_save_name(name: Any) -> str:
    """Return a safe save name, or refuse it.

    The name may not contain a path separator, may not start with a dot
    and may not be a reserved Windows device name.
    """
    if not isinstance(name, str):
        raise SaveError("The save name must be text")
    candidate = name.strip()
    if not candidate:
        raise SaveError("The save name must not be empty")
    if not candidate.lower().endswith(".zip"):
        candidate += ".zip"
    stem = candidate[:-4]
    if not SAVE_NAME_PATTERN.fullmatch(stem):
        raise SaveError(
            "The save name may use letters, digits, spaces, dots, "
            "underscores and dashes, and must start with a letter or a digit")
    reserved = {
        "con", "prn", "aux", "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
    if stem.split(".")[0].lower() in reserved:
        raise SaveError("That save name is reserved by Windows")
    return candidate


def _within(root: Path, candidate: Path) -> bool:
    """Whether a path stays inside a directory."""
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_save(root: Path, name: str) -> Path:
    """Return the path of one save inside a directory, or refuse it.

    The name is validated, the result is resolved, and the result must
    still be inside the directory. A symbolic link that points out of the
    tree is refused as well.
    """
    directory = Path(root)
    validated = validate_save_name(name)
    candidate = directory / validated
    try:
        resolved = candidate.resolve()
    except OSError:
        raise SaveError("The save could not be resolved") from None
    try:
        resolved.relative_to(directory.resolve())
    except ValueError:
        raise SaveError(
            "The save is outside the profile's own save directory") from None
    return resolved


def _read_level_metadata(path: Path) -> dict[str, Any]:
    """Return the metadata the save's ``level.dat`` really carries.

    Factorio writes the level information as JSON inside the archive. A
    save that is not a ZIP, or that has no readable ``level.dat``, yields
    an empty mapping and a problem, never a guess.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                name for name in archive.namelist()
                if name.endswith("/" + LEVEL_NAME)
                or name == LEVEL_NAME
            ]
            if not names:
                return {}
            with archive.open(names[0]) as handle:
                raw = handle.read(4 * 1024 * 1024)
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError,
            UnicodeError) as error:
        raise SaveError(
            f"The save could not be read: {type(error).__name__}") from None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def _mod_names(level: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the mods the save really records."""
    mod_list = level.get("mod_list")
    if not isinstance(mod_list, list):
        return ()
    names: list[str] = []
    for entry in mod_list:
        if isinstance(entry, Mapping):
            name = entry.get("name")
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    return tuple(names)


def _level_version(level: Mapping[str, Any]) -> str | None:
    """Return the game version the save records, when it records one."""
    for key in ("version", "game_version"):
        value = level.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _duration_text(level: Mapping[str, Any]) -> str | None:
    """Return the recorded session or play time, when there is one."""
    for key in ("playtime", "play_time", "session_time"):
        value = level.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return format_duration(float(value))
    return None


def format_duration(seconds: float) -> str:
    """Return a duration in the form the interface shows."""
    if seconds < 60:
        return f"{int(seconds)} s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


class SaveManager:
    """The saves of one profile, and the operations on them."""

    def __init__(self, saves_directory: Path,
                 *, backup_directory: Path | None = None) -> None:
        self.saves_directory = Path(saves_directory)
        self.backup_directory = (
            Path(backup_directory) if backup_directory is not None
            else self.saves_directory / BACKUP_FOLDER)

    # -- listing ---------------------------------------------------------

    def list_saves(self) -> tuple[SaveInfo, ...]:
        """Return the saves of the profile, newest first.

        Only the ``.zip`` files directly inside the profile's own saves
        directory are listed. The backup folder is not a save folder and
        is never listed as one.
        """
        directory = self.saves_directory
        if not directory.is_dir():
            return ()
        saves: list[SaveInfo] = []
        for entry in sorted(directory.iterdir()):
            if not entry.is_file() or entry.suffix.lower() != ".zip":
                continue
            saves.append(self.describe(entry))
        saves.sort(key=lambda item: item.modified, reverse=True)
        return tuple(saves)

    def describe(self, path: Path) -> SaveInfo:
        """Return what is really known about one save file."""
        path = Path(path)
        try:
            stat = path.stat()
            size = int(stat.st_size)
            modified = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        except OSError as error:
            return SaveInfo(
                name=path.name, path=path, size_bytes=0, modified="",
                game_version=None, mod_list=(), session_time=None,
                play_time=None, backups=(),
                problem=f"The save could not be read: {error}")
        backups = self.backups_of(path.name)
        if size > MAX_SAVE_BYTES:
            return SaveInfo(
                name=path.name, path=path, size_bytes=size, modified=modified,
                game_version=None, mod_list=(), session_time=None,
                play_time=None, backups=backups,
                problem="The save is larger than the manager reads")
        try:
            level = _read_level_metadata(path)
        except SaveError as error:
            return SaveInfo(
                name=path.name, path=path, size_bytes=size, modified=modified,
                game_version=None, mod_list=(), session_time=None,
                play_time=None, backups=backups, problem=str(error))
        if not level:
            return SaveInfo(
                name=path.name, path=path, size_bytes=size, modified=modified,
                game_version=None, mod_list=(), session_time=None,
                play_time=None, backups=backups,
                problem="The save carries no readable level information")
        return SaveInfo(
            name=path.name, path=path, size_bytes=size, modified=modified,
            game_version=_level_version(level),
            mod_list=_mod_names(level),
            session_time=_duration_text(level),
            play_time=_duration_text(level),
            backups=backups,
            problem=None)

    def backups_of(self, name: str) -> tuple[str, ...]:
        """Return the backups that exist for one save."""
        folder = self.backup_directory
        if not folder.is_dir():
            return ()
        stem = Path(name).stem
        return tuple(sorted(
            entry.name for entry in folder.iterdir()
            if entry.is_file() and entry.name.startswith(stem + BACKUP_SUFFIX)))

    # -- operations ------------------------------------------------------

    def backup(self, name: str) -> Path:
        """Copy a save into the backup folder and return the backup."""
        source = resolve_save(self.saves_directory, name)
        if not source.is_file():
            raise SaveError("The save does not exist")
        self.backup_directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        target = self.backup_directory / (
            f"{source.stem}{BACKUP_SUFFIX}.{stamp}.zip")
        counter = 1
        while target.exists():
            target = self.backup_directory / (
                f"{source.stem}{BACKUP_SUFFIX}.{stamp}.{counter}.zip")
            counter += 1
        shutil.copy2(source, target)
        return target

    def restore(self, backup_name: str, *, confirm: bool = False) -> Path:
        """Restore a save from a backup and return the restored path.

        The save that is replaced is backed up first, so a restore is
        itself recoverable.
        """
        if confirm is not True:
            raise SaveError("Restoring a save has to be confirmed")
        backup = self.backup_directory / Path(backup_name).name
        if not backup.is_file():
            raise SaveError("The backup does not exist")
        if not _within(self.backup_directory.resolve(), backup.resolve()):
            raise SaveError("The backup is outside the backup folder")
        target = resolve_save(self.saves_directory, backup.name.split(
            BACKUP_SUFFIX)[0] + ".zip")
        if target.exists():
            self.backup(target.name)
        _atomic_copy(backup, target)
        return target

    def rename(self, name: str, new_name: str, *,
               confirm: bool = False) -> Path:
        """Rename a save and return its new path."""
        if confirm is not True:
            raise SaveError("Renaming a save has to be confirmed")
        source = resolve_save(self.saves_directory, name)
        if not source.is_file():
            raise SaveError("The save does not exist")
        target = resolve_save(self.saves_directory, new_name)
        if target.exists():
            raise SaveError("A save with that name already exists")
        os.replace(source, target)
        return target

    def delete(self, name: str, *, confirm: bool = False) -> Path:
        """Delete a save after an explicit confirmation."""
        if confirm is not True:
            raise SaveError("Deleting a save has to be confirmed")
        target = resolve_save(self.saves_directory, name)
        if not target.is_file():
            raise SaveError("The save does not exist")
        # The backup is kept, so a mistaken delete stays recoverable.
        self.backup(target.name)
        target.unlink()
        return target

    def import_save(self, source: Path, name: str | None = None) -> Path:
        """Copy a save into the profile and return the new path."""
        origin = Path(source)
        if not origin.is_file():
            raise SaveError("The file to import does not exist")
        if origin.suffix.lower() != ".zip":
            raise SaveError("Only a Factorio save can be imported")
        target_name = name or origin.name
        target = resolve_save(self.saves_directory, target_name)
        if target.exists():
            raise SaveError("A save with that name already exists")
        _atomic_copy(origin, target)
        return target

    def export_save(self, name: str, destination: Path) -> Path:
        """Copy a save out of the profile and return the copy."""
        source = resolve_save(self.saves_directory, name)
        if not source.is_file():
            raise SaveError("The save does not exist")
        target = Path(destination)
        if target.exists():
            raise SaveError("The destination already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy(source, target)
        return target

    def compatibility(self, info: SaveInfo, *,
                      enabled_mods: Iterable[str] = (),
                      game_version: str | None = None) -> dict[str, Any]:
        """Report whether a save fits the profile's configuration.

        A save that records no mod list is **unknown**, not compatible: the
        game did not write one, so nothing can be proven.
        """
        enabled = {name for name in enabled_mods}
        if not info.mod_list:
            return {
                "status": "unknown",
                "detail": "The save records no mod list",
                "missing_mods": [],
                "extra_mods": [],
            }
        missing = sorted(name for name in info.mod_list if name not in enabled)
        extra = sorted(name for name in enabled if name not in info.mod_list)
        if game_version and info.game_version and \
                info.game_version != game_version:
            return {
                "status": "incompatible",
                "detail": (f"The save was written by Factorio "
                            f"{info.game_version}; the profile uses "
                            f"{game_version}"),
                "missing_mods": missing,
                "extra_mods": extra,
            }
        if missing:
            return {
                "status": "incompatible",
                "detail": ("The save needs mods that the profile does not "
                            "enable: " + ", ".join(missing)),
                "missing_mods": missing,
                "extra_mods": extra,
            }
        return {
            "status": "compatible",
            "detail": "Every mod the save needs is enabled",
            "missing_mods": [],
            "extra_mods": extra,
        }


def _atomic_copy(source: Path, target: Path) -> None:
    """Copy a file through a temporary file and rename it into place."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    os.close(handle)
    temporary_path = Path(temporary)
    try:
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, target)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
