"""Sync the versioned mod source into the local staging directory.

The live test profiles load the mod from
``.local/mod-test-mods/2.1.23/autoengineer-input_2.1.23``. The offline
regression test ``tests/test_mod_stage_consistency.py`` asserts that the
staged copy is byte-identical to the source, so every source change has
to be staged before a live run.

The script copies the source files and removes the staged files that no
longer exist in the source. It never touches the source, never touches a
save and never touches anything outside the staging directory.

Usage:

    python -B tests/sync_mod_stage.py
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
STAGED = ROOT / ".local" / "mod-test-mods" / "2.1.23" / "autoengineer-input_2.1.23"

#: The second active profile: the isolated installation's own portable mods
#: directory, which serves the Vanilla + Space Age profile.
VANILLA_PROFILE = Path(
    r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\mods"
) / "autoengineer-input_2.1.23"

#: Every directory the mod has to be staged into. Both are the two active
#: 2.1.23 test profiles documented in
#: ``memory/FACTORIO_TEST_PROFILE_ROUTING.md``.
STAGE_TARGETS = (STAGED, VANILLA_PROFILE)

#: The backup files the isolated environment keeps. They are not source
#: files and they are never removed by the sync.
BACKUP_SUFFIX = ".bak"


def digest(path: Path) -> str:
    """Return the SHA-256 of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files() -> list[Path]:
    """Return the relative source file list."""
    return sorted(
        path.relative_to(SOURCE)
        for path in SOURCE.rglob("*")
        if path.is_file() and not path.name.endswith(BACKUP_SUFFIX)
    )


def main() -> int:
    """Copy the source into every staging directory and report the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="only report what would change; do not copy")
    arguments = parser.parse_args()

    if not SOURCE.is_dir():
        print(f"ERROR: missing mod source {SOURCE}", file=sys.stderr)
        return 1

    files = source_files()
    for target_root in STAGE_TARGETS:
        added: list[str] = []
        changed: list[str] = []
        removed: list[str] = []

        for relative in files:
            target = target_root / relative
            source_file = SOURCE / relative
            if not target.is_file():
                added.append(str(relative))
            elif digest(target) != digest(source_file):
                changed.append(str(relative))
            else:
                continue
            if not arguments.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target)

        staged_files = {
            path.relative_to(target_root)
            for path in target_root.rglob("*")
            if path.is_file() and not path.name.endswith(BACKUP_SUFFIX)
        }
        # Only staged files that no longer exist in the source are removed.
        # The previous code used ``set(files) - staged_files``, which listed
        # source files that were merely missing from the stage and deleted
        # them after they had just been copied.
        for relative in sorted(staged_files - set(files)):
            removed.append(str(relative))
            if not arguments.check:
                (target_root / relative).unlink()

        verb = "would sync" if arguments.check else "synced"
        print(f"MOD STAGE {verb} {target_root}: {len(files)} source files, "
              f"{len(added)} added, {len(changed)} updated, {len(removed)} removed")
        for name in added:
            print(f"  added {name}")
        for name in changed:
            print(f"  updated {name}")
        for name in removed:
            print(f"  removed {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
