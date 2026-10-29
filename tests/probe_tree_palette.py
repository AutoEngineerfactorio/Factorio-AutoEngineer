"""Offline probe: extract the verified 2.1.23 tree tint palettes.

Factorio renders a tree on the map with the tree entity sprite tinted by the
tree prototype's ``colors`` property. These are the game's own tree colours.
Extract them from the verified 2.1.23 installation's data stage so the
dashboard can use the real values instead of an invented swatch.
"""
import io
import os
import re

GAME = r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22"
ROOT = r"D:\AI\Factorio-AutoEngineer-Source"
OUT = os.path.join(ROOT, ".local", "scratch", "tree_palette.txt")
out = io.open(OUT, "w", encoding="utf-8")


def w(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


p = os.path.join(GAME, "data", "base", "prototypes", "entity", "trees.lua")
text = io.open(p, encoding="utf-8", errors="replace").read()
lines = text.split("\n")

# Find each define_trees entry: its "type = N", "identifier = ..." and the
# "colors = { {r=..,g=..,b=..}, ... }" block.
entries = []
for i, line in enumerate(lines):
    type_match = re.search(r"^\s*type\s*=\s*(\d+),\s*$", line)
    if type_match:
        type_number = int(type_match.group(1))
        identifier = None
        colors = []
        for j in range(i + 1, min(len(lines), i + 60)):
            m = re.search(r'identifier\s*=\s*"([^"]+)"', lines[j])
            if m:
                identifier = m.group(1)
            if re.search(r"colors\s*=\s*$", lines[j]):
                for k in range(j + 1, min(len(lines), j + 30)):
                    cm = re.search(r"\{\s*r\s*=\s*(\d+)\s*,\s*g\s*=\s*(\d+)\s*,\s*b\s*=\s*(\d+)\s*\}",
                                   lines[k])
                    if cm:
                        colors.append(tuple(int(x) for x in cm.groups()))
                    elif re.search(r"^\s*\},?\s*$", lines[k]) and colors:
                        break
                break
            if re.search(r"get_water_reflection", lines[j]):
                break
        entries.append((type_number, identifier, colors))

w("=== tree tint palettes from data/base/prototypes/entity/trees.lua")
for type_number, identifier, colors in entries:
    name = "tree-%02d" % type_number
    if identifier:
        name += "_" + identifier
    w("  %-20s %d colours" % (name, len(colors)))
    for c in colors:
        w("       #%02x%02x%02x" % c)

# How the prototype name is built from the type number and identifier.
w("")
w("=== how the prototype name is built")
for i, line in enumerate(lines):
    if re.search(r'local type_name\s*=\s*"tree-"', line) or \
       re.search(r'name\s*=\s*name\s*\.\s*"-"', line):
        w("  %5d| %s" % (i + 1, line[:150]))
        for j in range(max(0, i - 6), min(len(lines), i + 8)):
            w("       %5d| %s" % (j + 1, lines[j][:150]))
        w("       " + "-" * 40)

out.close()
print("ok")
