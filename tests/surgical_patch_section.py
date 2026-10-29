"""Apply a **surgical** update to one section of the combined backend patch.

The combined patch stores each readable backend source as a new-file diff:

    --- /dev/null
    +++ b/FactorioMCP/Tools/AutoEngineerTools.cs
    @@ -0,0 +1,153 @@
    +<source line>
    ...

Regenerating a whole section rewrites every line of it, which produces a
diff far larger than the content that actually changed and blows the
small-chunk line budget. This script instead:

1. extracts the section's content lines,
2. compares them with the readable source,
3. replaces **only** the changed lines, and
4. rewrites the hunk header with the new line count.

The result is a minimal patch diff. The script verifies that the extracted
content and the readable source differ only by the intended change, so it
can never silently rewrite a section.

The script never touches the readable sources, the game, a save or
anything outside the patch file.

Usage:

    python -B tests/surgical_patch_section.py --check
    python -B tests/surgical_patch_section.py --apply
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import synthesize_backend_patch as synth  # noqa: E402

PATCH = ROOT / "backend-safety" / "backend-safety.patch"

#: The sections this script may update, mapped to their readable source.
SECTIONS: dict[str, str] = {
    "FactorioMCP/Tools/AutoEngineerTools.cs": "AutoEngineerTools.cs",
    "FactorioMCP/Tools/ModObservation.cs": "Tools/ModObservation.cs",
    "FactorioMCP/Tools/ViewComposer.cs": "Tools/ViewComposer.cs",
    "FactorioMCP/Tools/RecipeResearchAdapter.cs": "Tools/RecipeResearchAdapter.cs",
    "FactorioMCP/Tools/SafetyTools.cs": "SafetyTools.cs",
    "FactorioMCP/Services/NavigationPathPolicy.cs": "NavigationPathPolicy.cs",
    "FactorioMCP/Services/OperationService.cs": "OperationService.cs",
}

#: The maximum number of changed content lines one section may carry. A
#: larger change means the readable source moved too far and the update
#: has to be split into a reviewed change of its own.
MAX_SECTION_DELTA = 200


def section_content(section: str) -> list[str]:
    """Return the content lines of one new-file diff section."""
    return [
        line[1:] for line in section.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def rebuild_section(section: str, content: list[str]) -> str:
    """Return the section with new content and a corrected hunk header."""
    lines = section.splitlines(keepends=True)
    header = 0
    while header < len(lines) and not lines[header].startswith("@@"):
        header += 1
    if header >= len(lines):
        raise ValueError("the section has no hunk header")
    prefix = "".join(lines[:header])
    body = "".join("+" + line + "\n" for line in content)
    return f"{prefix}@@ -0,0 +1,{len(content)} @@\n{body}"


def main() -> int:
    """Report or apply the surgical section updates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="report the delta without writing")
    parser.add_argument("--apply", action="store_true",
                        help="write the surgical update")
    arguments = parser.parse_args()
    if not (arguments.check or arguments.apply):
        print("NO_MODE_SELECTED")
        return 2

    patch_text = PATCH.read_text(encoding="utf-8")
    sections = synth.split_sections(patch_text)

    updated: list[str] = []
    ordered: list[str] = []
    for target, text in sections:
        source_rel = SECTIONS.get(target)
        if source_rel is None:
            ordered.append(text)
            continue
        source_path = ROOT / "backend-safety" / source_rel
        if not source_path.is_file():
            ordered.append(text)
            continue
        content = section_content(text)
        source = source_path.read_text(encoding="utf-8").splitlines()
        if content == source:
            ordered.append(text)
            continue
        delta = list(difflib.unified_diff(content, source, lineterm="", n=0))
        changed = [line for line in delta
                   if line.startswith(("+", "-"))
                   and not line.startswith(("+++", "---"))]
        print(f"{target}: patch={len(content)} source={len(source)} "
              f"changed_lines={len(changed)}")
        if len(changed) > MAX_SECTION_DELTA:
            print(f"  REFUSED: {len(changed)} changed lines exceeds "
                  f"{MAX_SECTION_DELTA}")
            ordered.append(text)
            continue
        for line in delta:
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                print("   ", line)
        updated.append(target)
        ordered.append(rebuild_section(text, source))

    if not updated:
        print("NOTHING_TO_UPDATE")
        return 0

    if arguments.check:
        print("CHECK_ONLY")
        return 0

    result = "".join(ordered)
    if not result.endswith("\n"):
        result += "\n"
    PATCH.write_text(result, encoding="utf-8", newline="")
    print(f"APPLIED={','.join(updated)}")
    print(f"PATCH_BYTES={PATCH.stat().st_size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
