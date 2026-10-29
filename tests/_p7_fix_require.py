"""Fix the mod's require syntax for root-level Lua files.

Factorio's ``require`` resolves a path **relative to the mod root**, with the
segments separated by dots. The ``__modname__`` prefix names *another* mod.

The live server log proved the wrong form:

    Path __modname__/observation.lua does not match any enabled mod.

The installed mod ``PerfectlyGenericObject`` shows the correct form for a
mod's own root-level file:

    require("prototypes.item.perfectly-generic-object")

So this script rewrites every ``require("__modname__/<name>")`` into
``require("<name>")``.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOD = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
OUT = ROOT / "memory" / "_p7_require_fix.txt"

PATTERN = re.compile(r'require\("__modname__(?:/|\.)([A-Za-z0-9_]+)"\)')

lines = []
for path in sorted(MOD.glob("*.lua")):
    text = path.read_text(encoding="utf-8")
    fixed = PATTERN.sub(r'require("\1")', text)
    if fixed != text:
        path.write_text(fixed, encoding="utf-8", newline="")
        lines.append(f"CHANGED {path.name}")
    else:
        lines.append(f"unchanged {path.name}")

# Nothing may still use the cross-mod form.
remaining = []
for path in sorted(MOD.glob("*.lua")):
    text = path.read_text(encoding="utf-8")
    for match in PATTERN.finditer(text):
        remaining.append(f"{path.name}: {match.group(0)}")
lines.append("")
lines.append(f"remaining cross-mod requires: {remaining}")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written", OUT)
sys.exit(1 if remaining else 0)
