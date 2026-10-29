"""Regenerate the RecipeResearchAdapter.cs section of the combined backend patch.

The adapter is a NEW file in the patch (`--- /dev/null`). The readable copy in
backend-safety/Tools/RecipeResearchAdapter.cs is the single source of truth, so
the patch section is rebuilt from it with exact @@ line counts.

Uses difflib against an empty original so the result stays a new-file diff.
"""
import difflib
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
ADAPTER = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"
REL = "FactorioMCP/Tools/RecipeResearchAdapter.cs"


def main():
    new_text = ADAPTER.read_text(encoding="utf-8")
    new_lines = new_text.splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(
        [], new_lines, fromfile="/dev/null", tofile="b/" + REL, n=3,
    ))
    if not diff.strip():
        print("EMPTY_DIFF")
        return 3

    patch_text = PATCH.read_text(encoding="utf-8")
    marker = "--- /dev/null\n+++ b/" + REL + "\n"
    start = patch_text.find(marker)
    if start < 0:
        print("MARKER_NOT_FOUND")
        return 4
    # The adapter section is the last section of the patch.
    end = len(patch_text)
    updated = patch_text[:start] + diff
    if not updated.endswith("\n"):
        updated += "\n"
    PATCH.write_text(updated, encoding="utf-8", newline="")
    print("PATCH_BYTES=" + str(PATCH.stat().st_size))
    print("ADAPTER_LINES=" + str(len(new_lines)))
    print("REPLACED_FROM_OFFSET=" + str(start))
    print("TRAILING_BYTES_DROPPED=" + str(end - start - len(diff)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
