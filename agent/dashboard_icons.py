"""Safe icon path resolution for the Factorio 2.1.23 installation.

Prototype names arrive from game telemetry, so they are only ever used as a
single validated path segment inside the isolated installation's own icon
directories. Nothing here reads an arbitrary path supplied by telemetry.
"""
import json
import os
from pathlib import Path
from typing import Any

# The packages shipped with Factorio 2.1.23 that own item icons.
ICON_PACKAGES = ("base", "space-age", "quality", "elevated-rails", "recycler", "core")

# Quality tiers as observed in Factorio 2.1.23 (Space Age "quality" package).
QUALITY_ORDER = ("normal", "uncommon", "rare", "epic", "legendary")

# The 1x frame of a Factorio icon atlas is 64 pixels square.
ICON_FRAME = 64


def factorio_data_root() -> Path:
    """Prefer the verified isolated 2.1.23 installation over unrelated Steam data."""
    override = os.environ.get("AUTOENGINEER_FACTORIO_DATA")
    if override:
        return Path(override)
    return Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\data")


def factorio_mods_root() -> Path:
    """Return the local mods directory of the verified isolated installation."""
    override = os.environ.get("AUTOENGINEER_FACTORIO_MODS")
    if override:
        return Path(override)
    return Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\mods")


def enabled_mod_names(mods_root: Path) -> tuple[str, ...]:
    """Return the enabled mod directory names recorded by the local install.

    The list comes from the installation's own ``mod-list.json``; nothing here
    is influenced by telemetry.
    """
    try:
        raw = json.loads((Path(mods_root) / "mod-list.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(raw, dict):
        return ()
    mods = raw.get("mods")
    if not isinstance(mods, list):
        return ()
    names = []
    for entry in mods:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if is_safe_prototype_name(name) and entry.get("enabled") is not False:
            names.append(name)
    return tuple(names)


def is_safe_prototype_name(name: Any) -> bool:
    """True when a name can be used as a single path segment.

    Names arrive from game telemetry, so they are never allowed to carry a
    separator, a drive letter, a space or a non-ASCII character.
    """
    if not isinstance(name, str) or not name or len(name) > 128:
        return False
    return all(c.isascii() and (c.isalnum() or c in "-_") for c in name)


def icon_candidates(data_root: Path, name: Any) -> tuple[Path, ...]:
    """Return safe, local icon paths for a prototype name.

    The name is a prototype label, never an arbitrary filesystem path, so a
    name that could escape the icon directory yields no candidates at all.
    """
    if not is_safe_prototype_name(name):
        return ()
    return tuple(
        Path(data_root) / package / "graphics" / "icons" / (name + ".png")
        for package in ICON_PACKAGES
    )


def quality_icon_candidates(data_root: Path, quality: Any) -> tuple[Path, ...]:
    """Return the quality badge icon paths for a quality tier."""
    if not isinstance(quality, str) or quality not in QUALITY_ORDER or quality == "normal":
        return ()
    return tuple(
        Path(data_root) / package / "graphics" / "icons" / (f"quality-{quality}.png")
        for package in ("quality", "core", "base")
    )


def mod_icon_candidates(mods_root: Path, name: Any) -> tuple[Path, ...]:
    """Return the icon paths of a modded item inside the local mods folder.

    Only mod directories that the installation itself lists as enabled are
    searched, and the prototype name is validated as a single path segment.
    """
    if not is_safe_prototype_name(name):
        return ()
    root = Path(mods_root)
    paths = []
    for mod in enabled_mod_names(root):
        folders = [root / mod]
        if root.is_dir():
            # Factorio uses <mod_name>_<version> for unpacked mod folders.
            folders.extend(sorted(
                p for p in root.glob(mod + "_*")
                if p.is_dir() and not p.is_symlink()
                and p.name[len(mod) + 1:].replace(".", "").isdigit()
            ))
        paths.extend(
            folder / "graphics" / "icons" / (name + ".png")
            for folder in folders
        )
    return tuple(paths)


def all_icon_candidates(data_root: Path, mods_root: Path, name: Any) -> tuple[Path, ...]:
    """Return every icon path for a prototype, vanilla packages first."""
    return icon_candidates(data_root, name) + mod_icon_candidates(mods_root, name)


def icon_frame_geometry(width: int, height: int) -> tuple[int, int]:
    """Return the (frame size, frame count) of a Factorio icon atlas.

    Factorio stores icons as a horizontal mipmap strip: the 1x frame is the
    full 64 pixel icon, followed by the 2x, 4x and 8x frames, so the common
    120x64 file holds four frames of 64, 32, 16 and 8 pixels.
    """
    if width <= 0 or height <= 0:
        return 0, 0
    edge = min(width, height)
    frames = 0
    remaining = width
    size = edge
    while remaining >= size and size > 0:
        frames += 1
        remaining -= size
        size //= 2
    return edge, max(1, frames)
