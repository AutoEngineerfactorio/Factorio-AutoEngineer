"""Analyse the Factorio map tree colour relative to the tile map colours.

Factorio shades a tile's map colour by a factor for uncharted/uncharted
chunks and draws natural overlays (trees, rocks) on top. Compare the measured
minimap pixels with the verified tile map colours to find the relationship.
"""
import io
import os

from PIL import Image

ROOT = r"D:\AI\Factorio-AutoEngineer-Source"
PNG = os.path.join(ROOT, ".local", "scratch", "r08_factorio_window.png")
OUT = os.path.join(ROOT, ".local", "scratch", "map_ratio.txt")
out = io.open(OUT, "w", encoding="utf-8")

# Verified 2.1.23 tile map colours.
TILE = {
    "grass-1": (55, 53, 11),
    "grass-2": (66, 57, 15),
    "grass-3": (65, 52, 28),
    "grass-4": (59, 40, 18),
    "dry-dirt": (94, 66, 37),
    "dirt-1": (141, 104, 60),
    "dirt-2": (136, 96, 59),
    "dirt-3": (133, 92, 53),
    "dirt-4": (103, 72, 43),
    "dirt-5": (91, 63, 38),
    "dirt-6": (80, 55, 31),
    "dirt-7": (80, 54, 28),
    "sand-1": (138, 103, 58),
    "sand-2": (128, 93, 52),
    "sand-3": (115, 83, 47),
    "water": (51, 83, 95),
    "water-shallow": (82, 98, 92),
}

image = Image.open(PNG).convert("RGB")
width, height = image.size
region = image.crop((int(width * 0.83), int(height * 0.10),
                     int(width * 0.995), int(height * 0.38)))
pixels: list[tuple[int, int, int]] = [
    region.getpixel((x, y))  # type: ignore[misc]
    for y in range(region.height)
    for x in range(region.width)
]

out.write("minimap pixels: %d\n" % len(pixels))

# For every measured pixel, find the tile colour it best matches at a
# constant shading factor, and report the factor distribution.
best_factors = {}
for pixel in pixels:
    for name, tile in TILE.items():
        for factor in (1.0, 0.9, 0.8, 0.75, 0.7, 0.6667, 0.6, 0.5):
            expected = tuple(int(round(c * factor)) for c in tile)
            if expected == pixel:
                best_factors[(name, factor)] = best_factors.get((name, factor), 0) + 1

out.write("\nmeasured pixel -> tile colour matches:\n")
for (name, factor), count in sorted(best_factors.items(), key=lambda i: -i[1])[:20]:
    out.write("   %-14s x%.4f  %d pixels\n" % (name, factor, count))

# The green overlay pixels: compare them with the tile colours of the tiles
# they sit on to derive the overlay tint.
out.write("\ngreen overlay pixels (dark) and the ratio to a mid dirt tile:\n")
dirt1 = TILE["dirt-1"]
greens = [p for p in pixels if p[1] > p[0] + 12 and p[1] > p[2] + 12]
greens.sort(key=lambda p: -sum(p))
for pixel in greens[:12]:
    ratios = tuple(round(pixel[i] / dirt1[i], 3) if dirt1[i] else None for i in range(3))
    out.write("   #%02x%02x%02x  ratio to dirt-1 %s\n"
              % (pixel[0], pixel[1], pixel[2], ratios))

out.close()
print("ok")
