"""Regenerate the AutoEngineerTools.cs section of the combined backend patch.

The tools file is a NEW file in the patch (``--- /dev/null``). The readable
copy in ``backend-safety/AutoEngineerTools.cs`` is the single source of truth,
so the patch section is rebuilt from it with exact @@ line counts.

Uses difflib against an empty original so the result stays a new-file diff,
the same approach ``tests/synthesize_adapter_patch.py`` uses for the adapter.
"""
import difflib
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
TOOLS = ROOT / "backend-safety" / "AutoEngineerTools.cs"
REL = "FactorioMCP/Tools/AutoEngineerTools.cs"


def main():
    new_text = TOOLS.read_text(encoding="utf-8")
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
    # The tools section ends where the next "--- " file header starts.
    rest = patch_text[start + len(marker):]
    next_header = rest.find("\n--- ")
    if next_header < 0:
        end = len(patch_text)
    else:
        end = start + len(marker) + next_header + 1
    updated = patch_text[:start] + diff
    if not updated.endswith("\n"):
        updated += "\n"
    updated += patch_text[end:]
    PATCH.write_text(updated, encoding="utf-8", newline="")
    print("PATCH_BYTES=" + str(PATCH.stat().st_size))
    print("TOOLS_LINES=" + str(len(new_lines)))
    print("SECTION_START=" + str(start))
    print("SECTION_END=" + str(end))
    return 0


if __name__ == "__main__":
    sys.exit(main())
