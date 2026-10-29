"""Measure the factor Factorio applies to a tree tint when drawing it on the
MAP, by comparing the live minimap tree pixels with the verified 2.1.23 tree
tint palettes.

If the factor is consistent across many measured pixels, it is the map
shading factor and can be applied exactly.
"""
import collections
import io
import os
import sys
from typing import TypeAlias

from PIL import Image

Rgb: TypeAlias = tuple[int, int, int]

ROOT = r"D:\AI\Factorio-AutoEngineer-Source"
sys.path.insert(0, os.path.join(ROOT, "agent"))
import dashboard_nature_layers as nature  # noqa: E402

PNG = os.path.join(ROOT, ".local", "scratch", "r08_factorio_window.png")
OUT = os.path.join(ROOT, ".local", "scratch", "map_factor.txt")
out = io.open(OUT, "w", encoding="utf-8")

image = Image.open(PNG).convert("RGB")
width, height = image.size
region = image.crop((int(width * 0.83), int(height * 0.10),
                     int(width * 0.995), int(height * 0.38)))
pixels: list[Rgb] = []
for y in range(region.height):
    for x in range(region.width):
        pixel = region.getpixel((x, y))
        if isinstance(pixel, tuple) and len(pixel) == 3:
            red, green, blue = pixel
            pixels.append((int(red), int(green), int(blue)))

# Every verified tree tint as an RGB triple.
tints: list[Rgb] = []
for palette in nature.VERIFIED_TREE_TINT_PALETTES.values():
    for value in palette:
        tints.append((int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)))

out.write("minimap pixels: %d, tree tints: %d\n" % (len(pixels), len(tints)))

# For each green-dominant pixel, find the tint and the factor that explain it.
factors = collections.Counter()
best_rows = []
for pixel in pixels:
    if not (pixel[1] > pixel[0] + 8 and pixel[1] > pixel[2] + 8):
        continue
    for tint in tints:
        if tint[0] == 0 or tint[1] == 0:
            continue
        factor = pixel[1] / tint[1]
        if factor <= 0:
            continue
        expected = tuple(int(round(c * factor)) for c in tint)
        if expected == pixel:
            factors[round(factor, 3)] += 1
            best_rows.append((pixel, tint, round(factor, 3)))
            break

out.write("\ntint x factor combinations that exactly explain a map pixel:\n")
for factor, count in factors.most_common(20):
    out.write("   factor %.3f  ->  %d pixels\n" % (factor, count))

out.write("\nsample explanations:\n")
for pixel, tint, factor in best_rows[:25]:
    out.write("   map #%02x%02x%02x  = tint #%02x%02x%02x  x %.3f\n"
              % (pixel[0], pixel[1], pixel[2], tint[0], tint[1], tint[2], factor))

# The dominant factor, and the map colour it predicts for each tint.
out.write("\nif the dominant factor is F, the map tree colours are:\n")
if factors:
    dominant = factors.most_common(1)[0][0]
    for name, palette in sorted(nature.VERIFIED_TREE_TINT_PALETTES.items()):
        out.write("   %-16s %s\n" % (name, [c for c in palette][:4]))
out.close()
print("ok")
