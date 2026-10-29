"""Rebuild the missing file sections of the combined backend patch.

The readable copies under ``backend-safety/`` are the single source of truth
for the restricted backend.  The combined ``backend-safety.patch`` must carry
those exact bytes for every file the patched ``.csproj`` compiles, otherwise
the patch cannot be applied and built on the pinned upstream checkout.

This script is idempotent: each section is replaced when it is present and
appended when it is missing.  It never invents content, never touches the
readable sources, and never touches the game.

Sections are emitted as new-file diffs (``--- /dev/null``) with exact ``@@``
line counts, which is the same shape the existing ``synthesize_*_patch.py``
helpers produce.
"""
from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "backend-safety" / "backend-safety.patch"

# (relative source path under backend-safety/, path inside the upstream tree)
SECTIONS: tuple[tuple[str, str], ...] = (
    ("AutoEngineerTools.cs", "FactorioMCP/Tools/AutoEngineerTools.cs"),
    ("SafetyTools.cs", "FactorioMCP/Tools/SafetyTools.cs"),
    ("NavigationPathPolicy.cs", "FactorioMCP/Services/NavigationPathPolicy.cs"),
    ("OperationService.cs", "FactorioMCP/Services/OperationService.cs"),
    ("Tools/RecipeResearchAdapter.cs", "FactorioMCP/Tools/RecipeResearchAdapter.cs"),
    ("Tools/ModObservation.cs", "FactorioMCP/Tools/ModObservation.cs"),
    ("Tools/ViewComposer.cs", "FactorioMCP/Tools/ViewComposer.cs"),
)

# The NuGet lockfile is not a readable source in this checkout: it is a
# generated artifact that the patched .csproj requires
# (``RestorePackagesWithLockFile``) so the offline restore stays reproducible.
# It is therefore restored verbatim from the committed patch rather than
# regenerated, and it is never edited.
LOCKFILE_TARGET = "FactorioMCP/packages.lock.json"


def new_file_diff(source_text: str, rel: str) -> str:
    """Return a unified diff that creates ``rel`` with exactly ``source_text``."""
    new_lines = source_text.splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            [], new_lines, fromfile="/dev/null", tofile="b/" + rel, n=3,
        )
    )
    if not diff.strip():
        raise ValueError(f"empty diff for {rel}")
    return diff


def split_sections(patch_text: str) -> list[tuple[str, str]]:
    """Split a combined patch into (target path, section text) pairs.

    This patch uses plain ``--- a/`` / ``+++ b/`` headers without
    ``diff --git`` lines, so a section is delimited by its ``+++ b/`` header
    and runs up to the next section's ``--- a/`` header.  The ``--- a/``
    header belongs to the section it opens.
    """
    lines = patch_text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("--- ")]
    sections: list[tuple[str, str]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        chunk = lines[start:end]
        target = None
        for line in chunk:
            if line.startswith("+++ b/"):
                target = line[len("+++ b/"):].rstrip("\n")
                break
        if target is not None:
            sections.append((target, "".join(chunk)))
    return sections


def committed_lockfile_section() -> str | None:
    """Return the committed patch's ``packages.lock.json`` section verbatim.

    The lockfile is a generated NuGet artifact with no readable copy in this
    checkout.  It is restored from the committed patch so the offline restore
    stays reproducible; it is never regenerated or edited.
    """
    committed = subprocess.run(
        ["git", "show", "HEAD:backend-safety/backend-safety.patch"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if committed.returncode != 0:
        return None
    for target, text in split_sections(committed.stdout):
        if target == LOCKFILE_TARGET:
            return text
    return None


def rebuild(selected: tuple[str, ...] | None = None) -> int:
    patch_text = PATCH.read_text(encoding="utf-8")
    sections = split_sections(patch_text)
    by_target = {target: text for target, text in sections}

    wanted = [pair for pair in SECTIONS
              if selected is None or pair[0] in selected]
    if not wanted:
        print("NO_SECTION_SELECTED")
        return 2

    added: list[str] = []
    replaced: list[str] = []
    for source_rel, target_rel in wanted:
        source_path = ROOT / "backend-safety" / source_rel
        if not source_path.exists():
            print(f"MISSING_SOURCE {source_rel}")
            return 3
        source_text = source_path.read_text(encoding="utf-8")
        diff = new_file_diff(source_text, target_rel)
        if target_rel in by_target:
            if by_target[target_rel] == diff:
                continue
            replaced.append(target_rel)
        else:
            added.append(target_rel)
        by_target[target_rel] = diff

    # The lockfile is restored from the committed patch, never regenerated.
    if selected is None or "packages.lock.json" in selected:
        if LOCKFILE_TARGET not in by_target:
            lock_section = committed_lockfile_section()
            if lock_section is None:
                print("LOCKFILE_NOT_FOUND_IN_COMMITTED_PATCH")
                return 4
            by_target[LOCKFILE_TARGET] = lock_section
            added.append(LOCKFILE_TARGET)

    if not added and not replaced:
        print("PATCH_ALREADY_CURRENT")
        print("PATCH_BYTES=" + str(PATCH.stat().st_size))
        return 0

    # Preserve the original section order, then append genuinely new sections.
    ordered: list[str] = []
    for target, text in sections:
        ordered.append(by_target.get(target, text))
    for source_rel, target_rel in SECTIONS:
        if target_rel in added:
            ordered.append(by_target[target_rel])
    if LOCKFILE_TARGET in added:
        ordered.append(by_target[LOCKFILE_TARGET])

    updated = "".join(ordered)
    if not updated.endswith("\n"):
        updated += "\n"
    PATCH.write_text(updated, encoding="utf-8", newline="")

    print("ADDED=" + (",".join(added) if added else "(none)"))
    print("REPLACED=" + (",".join(replaced) if replaced else "(none)"))
    print("PATCH_BYTES=" + str(PATCH.stat().st_size))
    return 0


if __name__ == "__main__":
    # ``--only`` restricts the run to named source sections so a large
    # restoration can be split into separately guarded chunks.  ``all`` and
    # an empty selection restore every section.
    args = sys.argv[1:]
    selected: tuple[str, ...] | None = None
    if args and args[0] == "--only":
        names = tuple(name for name in args[1:] if name)
        selected = None if (not names or "all" in names) else names
    sys.exit(rebuild(selected))
