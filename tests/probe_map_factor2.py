"""Measure Factorio's map tree colour precisely.

Only count pixels whose 8 neighbours are all the same colour, so the sample
contains no antialiased edge pixels. Those are the pure rendered tree
pixels and reveal the exact relationship between the tree's sprite tint and
the colour Factorio draws on the map.
"""
import collections
import io
import os
import sys

from PIL import Image

ROOT = r"D:\AI\Factorio-AutoEngineer-Source"
sys.path.insert(0, os.path.join(ROOT, "agent"))
import dashboard_nature_layers as nature  # noqa: E402

PNG = os.path.join(ROOT, ".local", "scratch", "r08_factorio_window.png")
OUT = os.path.join(ROOT, ".local", "scratch", "map_factor_pure.txt")
out = io.open(OUT, "w", encoding="utf-8")

image = Image.open(PNG).convert("RGB")
width, height = image.size
left = int(width * 0.83)
top = int(height * 0.10)
right = int(width * 0.995)
bottom = int(height * 0.38)
region = image.crop((left, top, right, bottom))
pixels = [region.getpixel((x, y))
          for y in range(region.height) for x in range(region.width)]
cols = region.size[0]
rows = region.size[1]

# Pure pixels: all 8 neighbours identical.
pure = []
for index in range(len(pixels)):
    x = index % cols
    y = index // cols
    if x < 1 or y < 1 or x >= cols - 1 or y >= rows - 1:
        continue
    pixel = pixels[index]
    if all(pixels[index + dy * cols + dx] == pixel
           for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
        pure.append(pixel)

out.write("minimap pixels: %d, pure (unantialiased) pixels: %d\n"
          % (len(pixels), len(pure)))

greens = [p for p in pure if p[1] > p[0] + 8 and p[1] > p[2] + 8]
counter = collections.Counter(greens)
out.write("\npure green-dominant pixels: %d\n" % len(greens))
out.write("their colours:\n")
for colour, count in counter.most_common(20):
    out.write("   #%02x%02x%02x  %d\n" % (colour[0], colour[1], colour[2], count))

tints = []
for palette in nature.VERIFIED_TREE_TINT_PALETTES.values():
    for value in palette:
        tints.append((int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)))

out.write("\nexact tint x factor explanations for the pure pixels:\n")
factors = collections.Counter()
for pixel in greens:
    for tint in tints:
        if tint[1] == 0:
            continue
        factor = pixel[1] / tint[1]
        expected = tuple(int(round(c * factor)) for c in tint)
        if expected == pixel:
            factors[round(factor, 3)] += 1
            out.write("   #%02x%02x%02x = tint #%02x%02x%02x x %.3f\n"
                      % (pixel[0], pixel[1], pixel[2], tint[0], tint[1], tint[2], factor))
            break

out.write("\nfactor histogram:\n")
for factor, count in factors.most_common(15):
    out.write("   %.3f -> %d\n" % (factor, count))

out.close()
print("ok")
