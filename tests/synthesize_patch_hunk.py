"""Synthesize the RconConnectionService.cs hunk of the combined backend patch.

Reads the pristine upstream file and the desired patched file, then writes a
valid unified diff hunk with correct @@ line counts. The hunk replaces the
existing RconConnectionService.cs section of backend-safety/backend-safety.patch.

Uses difflib.unified_diff so the counts are always consistent with the content.
"""
import difflib
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
UPSTREAM = Path(r"D:\AI\Factorio-AutoEngineer\FactorioMCP")
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
NEW_FILE = ROOT / "backend-safety" / "RconConnectionService.cs"
REL = "FactorioMCP/Services/RconConnectionService.cs"


def build_hunk(old_text, new_text):
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile="a/" + REL, tofile="b/" + REL, n=3,
    ))
    # difflib emits "--- a/...\n+++ b/...\n@@ ..."; keep the whole block.
    return "".join(diff)


def main():
    upstream_file = UPSTREAM / REL
    if not upstream_file.is_file():
        print("MISSING_UPSTREAM_FILE")
        return 2
    old_text = upstream_file.read_text(encoding="utf-8")
    new_text = NEW_FILE.read_text(encoding="utf-8")
    hunk = build_hunk(old_text, new_text)
    if not hunk.strip():
        print("EMPTY_HUNK")
        return 3

    patch_text = PATCH.read_text(encoding="utf-8")
    marker = "--- a/" + REL + "\n"
    start = patch_text.find(marker)
    if start < 0:
        print("MARKER_NOT_FOUND")
        return 4
    next_marker = "--- a/FactorioMCP/Tools/MovementTools.cs\n"
    end = patch_text.find(next_marker, start)
    if end < 0:
        print("NEXT_MARKER_NOT_FOUND")
        return 5
    updated = patch_text[:start] + hunk + patch_text[end:]
    PATCH.write_text(updated, encoding="utf-8", newline="")
    print("HUNK_LINES=" + str(len(hunk.splitlines())))
    print("PATCH_BYTES=" + str(PATCH.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
